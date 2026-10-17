"""Roomless Gemini Live session, controlled from the desktop worker thread."""
from __future__ import annotations

import asyncio
import os
import traceback
from pathlib import Path
from threading import Event
from types import SimpleNamespace


class VoiceSetupError(Exception):
    """A safe, user-facing setup error; never includes provider exception text."""

    def __init__(self, message, stage="configuration", error_type=None, frames=()):
        super().__init__(message)
        self.stage = stage
        self.error_type = error_type
        self.frames = frames


def setup_step(stage, callback):
    try:
        return callback()
    except VoiceSetupError:
        raise
    except Exception as error:
        names = {"audio_import": "chargement audio", "macos_tools": "outils macOS",
                 "gemini_model": "modèle Gemini", "agent_session": "session LiveKit"}
        frames = tuple(f"{Path(frame.filename).name}:{frame.lineno} ({frame.name})"
                       for frame in traceback.extract_tb(error.__traceback__)[-5:])
        raise VoiceSetupError(
            f"Le vocal bloque à l’étape « {names[stage]} » ({type(error).__name__}). "
            f"Code : {stage}. Lancez python scripts/diagnose_desktop_voice.py pour le diagnostic.",
            stage=stage, error_type=type(error).__name__, frames=frames,
        ) from None


def prepare_environment():
    try:
        from dotenv import dotenv_values
    except ImportError:
        raise VoiceSetupError("Installez le vocal : python -m pip install -e '.[desktop,live]'") from None
    allowed = {"GOOGLE_API_KEY", "JARVIS_GEMINI_LIVE_MODEL", "JARVIS_GEMINI_LIVE_VOICE",
               "JARVIS_GEMINI_LIVE_TEMPERATURE", "JARVIS_VISION_ENABLED"}
    # Explicit terminal env wins, then the user's desktop config, then repo .env.
    for path in (Path.home() / "Library/Application Support/Jarvis/desktop.env",
                 Path(__file__).resolve().parents[3] / ".env"):
        if path.is_file():
            for key, value in dotenv_values(path, interpolate=False).items():
                if key in allowed and value is not None:
                    os.environ.setdefault(key, value)
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        raise VoiceSetupError("Clé Gemini manquante. Ajoutez GOOGLE_API_KEY dans le fichier .env du projet "
                              "ou dans ~/Library/Application Support/Jarvis/desktop.env, puis réessayez.")


def create_components():
    try:
        from livekit.agents import Agent, AgentSession
        from livekit.plugins import google
        from jarvis.desktop.live_audio import LocalAudio
        from jarvis.live.config import get_live_config
        from jarvis.live.factory import create_assistant_class, create_realtime_model
        from jarvis.live.logging import install_livekit_pii_log_filter
    except (ImportError, OSError):
        raise VoiceSetupError("Dépendances audio indisponibles. Installez python -m pip install -e '.[desktop,live]'.") from None
    install_livekit_pii_log_filter()
    try:
        config = get_live_config()
    except (ValueError, TypeError):
        raise VoiceSetupError("Configuration Gemini invalide. Vérifiez le modèle, la voix et la température.") from None
    audio = setup_step("audio_import", lambda: LocalAudio(asyncio.get_running_loop()))
    assistant = setup_step("macos_tools", lambda: create_assistant_class(Agent)())
    model = setup_step("gemini_model", lambda: create_realtime_model(google, config))
    # Gemini handles turn detection. No inference service or LiveKit room/token.
    session = setup_step("agent_session", lambda: AgentSession(llm=model, vad=None, turn_handling={
        "turn_detection": "realtime_llm",
        "interruption": {"resume_false_interruption": False},
    }))
    return SimpleNamespace(model=model, session=session,
        assistant=assistant, audio=audio)


class LiveRuntime:
    def __init__(self, emit, factory=create_components, prepare=prepare_environment):
        self.emit = emit
        self.factory = factory
        self.prepare = prepare
        self.stop_requested = Event()
        self.mute_requested = Event()
        self.interrupt_requested = Event()
        self.ready = False
        self.failed = False
        self.agent_state = "listening"
        self.components = None
        self.interruption_task = None

    def stop(self):
        self.stop_requested.set()

    def set_muted(self, muted):
        self.mute_requested.set() if muted else self.mute_requested.clear()

    def interrupt(self):
        self.interrupt_requested.set()

    def state(self, state):
        audio = self.components.audio if self.components else None
        self.emit({"type": "state", "state": state, "mic_open": bool(audio and audio.mic_open)})

    def _agent_changed(self, event):
        self.agent_state = event.new_state
        if self.ready and not self.stop_requested.is_set():
            self.state("muted" if self.mute_requested.is_set() else self.agent_state)

    def _conversation(self, event):
        item = event.item
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", "")
        if role in {"user", "assistant"} and isinstance(text, str) and text.strip():
            self.emit({"type": "transcript", "role": role, "text": text[:16000],
                       "interrupted": bool(getattr(item, "interrupted", False))})

    def _error(self, event):
        if not getattr(event.error, "recoverable", False):
            self.failed = True
            self.stop()

    def _closed(self, event):
        self.failed = self.failed or getattr(event, "error", None) is not None
        self.stop()

    @staticmethod
    def _consume_interruption(task):
        if not task.cancelled():
            task.exception()  # Consume races with a speech that already ended.

    async def _start(self):
        c = self.components
        task = asyncio.create_task(c.session.start(agent=c.assistant, record=False))
        try:
            while not task.done() and not self.stop_requested.is_set():
                await asyncio.wait({task}, timeout=0.05)
            if self.stop_requested.is_set():
                return False
            await task
            return True
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def run(self):
        phase = "setup"
        error_message = None
        try:
            if self.stop_requested.is_set():
                return
            self.prepare()
            self.components = self.factory()
            c = self.components
            c.session.input.audio = c.audio.input
            c.session.output.audio = c.audio.output
            c.session.on("agent_state_changed", self._agent_changed)
            c.session.on("conversation_item_added", self._conversation)
            c.session.on("error", self._error)
            c.session.on("close", self._closed)
            phase = "connection"
            started = await asyncio.wait_for(self._start(), timeout=30)
            if not started or self.stop_requested.is_set():
                return
            phase = "audio"
            c.audio.open()  # Micro state becomes active only after device start.
            self.ready = True
            self.state("listening")
            phase = "session"
            from jarvis.live.prompts import LIVE_SESSION_GREETING
            c.session.generate_reply(instructions=LIVE_SESSION_GREETING)
            while not self.stop_requested.is_set():
                wanted = not self.mute_requested.is_set()
                if wanted != c.audio.mic_open:
                    c.audio.set_microphone(wanted)
                    self.state(self.agent_state if wanted else "muted")
                if self.interrupt_requested.is_set():
                    self.interrupt_requested.clear()
                    if self.interruption_task is None or self.interruption_task.done():
                        try:
                            self.interruption_task = asyncio.ensure_future(c.session.interrupt())
                            self.interruption_task.add_done_callback(self._consume_interruption)
                        except RuntimeError:
                            pass  # Speech may already have finished.
                await asyncio.sleep(0.05)
            if self.failed:
                error_message = "La session Gemini s’est interrompue. Vérifiez la connexion, la clé et le modèle, puis relancez le vocal."
        except VoiceSetupError as error:
            error_message = str(error)
        except Exception:
            error_message = {
                "setup": "Le vocal n’a pas pu être préparé. Vérifiez les dépendances et les autorisations macOS.",
                "connection": "Connexion Gemini impossible. Vérifiez la clé, le modèle et l’accès Internet.",
                "audio": "Micro ou sortie audio indisponible. Vérifiez les périphériques et l’autorisation Microphone dans les réglages macOS.",
                "session": "La session vocale a rencontré un problème. Vérifiez la connexion et les périphériques audio.",
            }[phase]
        finally:
            self.ready = False
            c = self.components
            if c is not None:
                # Cut capture/playback before any potentially slow tool cleanup.
                try:
                    c.audio.close()
                except Exception:
                    error_message = "La fermeture audio a rencontré un problème. Vérifiez les périphériques avant de relancer."
                self.state("stopping")
                if self.interruption_task is not None:
                    self.interruption_task.cancel()
                    await asyncio.gather(self.interruption_task, return_exceptions=True)
                try:
                    await c.assistant.registry.aclose()
                except Exception:
                    error_message = error_message or "Une tâche vocale n’a pas pu être fermée correctement. Vérifiez son résultat avant de réessayer."
                for close in (c.session.aclose, c.model.aclose):
                    try:
                        await close()
                    except Exception:
                        error_message = error_message or "La session vocale n’a pas pu être fermée correctement. Vérifiez les actions en cours."
            if self.failed and not error_message:
                error_message = "La connexion Gemini s’est interrompue. Vérifiez la clé, le modèle et Internet."
            self.emit({"type": "state", "state": "error" if error_message else "off",
                       "mic_open": False, "message": error_message or ""})
