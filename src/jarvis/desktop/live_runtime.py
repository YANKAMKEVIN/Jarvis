"""Roomless Gemini Live session, controlled from the desktop worker thread."""
from __future__ import annotations

import asyncio
import os
import traceback
from collections import deque
from pathlib import Path
from threading import Event
from time import monotonic
from queue import Empty, SimpleQueue
from types import SimpleNamespace
import uuid

from jarvis.desktop.presentation import project_activity, project_task
from jarvis.desktop.devices import AudioDeviceError


class VoiceSetupError(Exception):
    """A safe, user-facing setup error; never includes provider exception text."""

    def __init__(self, message, stage="configuration", error_type=None, frames=()):
        super().__init__(message)
        self.stage = stage
        self.error_type = error_type
        self.frames = frames


def setup_failure(stage, error):
    names = {"environment": "configuration d’environnement", "sdk_import": "import du SDK",
             "logging": "journalisation", "audio_import": "chargement audio",
             "macos_tools": "outils macOS", "gemini_model": "modèle Gemini",
             "agent_session": "session LiveKit"}
    frames = tuple(f"{Path(frame.filename).name}:{frame.lineno} ({frame.name})"
                   for frame in traceback.extract_tb(error.__traceback__)[-5:])
    return VoiceSetupError(
        f"Le vocal bloque à l’étape « {names[stage]} » ({type(error).__name__}). "
        f"Code : {stage}. Lancez python scripts/diagnose_desktop_voice.py --worker.",
        stage=stage, error_type=type(error).__name__, frames=frames,
    )


def setup_step(stage, callback):
    try:
        return callback()
    except VoiceSetupError:
        raise
    except Exception as error:
        raise setup_failure(stage, error) from None


def prepare_environment():
    try:
        from dotenv import dotenv_values
    except ImportError:
        raise VoiceSetupError("Installez le vocal : python -m pip install -e '.[desktop,live]'") from None
    allowed = {"GOOGLE_API_KEY", "JARVIS_GEMINI_LIVE_MODEL", "JARVIS_GEMINI_LIVE_VOICE",
               "JARVIS_GEMINI_LIVE_TEMPERATURE", "JARVIS_VISION_ENABLED",
               "JARVIS_PLANNER_BACKEND", "JARVIS_PLANNER_MODEL", "JARVIS_GEMINI_PLANNER_MODEL",
               "JARVIS_PLANNER_NUM_CTX", "JARVIS_PLANNER_TIMEOUT", "JARVIS_LLM_MODEL"}
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


def preload_live_plugins():
    """Register LiveKit plugins on the main thread, before any voice worker.

    GooglePlugin registers itself at import and LiveKit explicitly rejects
    registration on background threads. This opens no devices or connection.
    """
    try:
        from livekit.plugins import google  # noqa: F401
    except (ImportError, OSError):
        raise VoiceSetupError("Dépendances Live indisponibles. Installez python -m pip install -e '.[desktop,live]'.") from None
    except Exception as error:
        raise setup_failure("sdk_import", error) from None


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
    except Exception as error:
        raise setup_failure("sdk_import", error) from None
    setup_step("logging", install_livekit_pii_log_filter)
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


ANNOUNCEMENT_MAX_AGE = 120.0
ANNOUNCEMENT_GAP = 5.0  # lets the agent state leave "listening" before the next one


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
        self.seen_items = deque(maxlen=512)
        self.sounds_requested = Event()
        self.cancel_task_requested = Event()
        self.task_cancellations = SimpleQueue()
        self.observed_tools = set()
        self.last_task_snapshot = None
        self.input_choice = self.output_choice = None
        self.closing = False
        self.announcements = SimpleQueue()

    def set_devices(self, input_choice, output_choice):
        self.input_choice, self.output_choice = input_choice, output_choice

    def set_sounds(self, enabled):
        self.sounds_requested.set() if enabled else self.sounds_requested.clear()

    def cancel_task(self, task_id=None):
        self.task_cancellations.put(task_id)
        self.cancel_task_requested.set()

    def stop(self):
        self.stop_requested.set()

    def set_muted(self, muted):
        self.mute_requested.set() if muted else self.mute_requested.clear()

    def interrupt(self):
        self.interrupt_requested.set()

    def announce(self, message):
        """Queue a proactive alert; spoken only once Jarvis is idle, never over a reply."""
        self.announcements.put((monotonic(), message))

    def state(self, state):
        audio = self.components.audio if self.components else None
        self.emit({"type": "state", "state": state, "mic_open": bool(audio and audio.mic_open),
                   "input_suppressed": bool(audio and getattr(audio, "input_suppressed", False))})

    def _agent_changed(self, event):
        self.agent_state = event.new_state
        if self.ready and not self.stop_requested.is_set():
            self.state("muted" if self.mute_requested.is_set() else self.agent_state)

    def _conversation(self, event):
        item = event.item
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", "")
        if role in {"user", "assistant"} and isinstance(text, str) and text.strip():
            item_id = getattr(item, "id", None)
            if item_id:
                if item_id in self.seen_items:
                    return
                self.seen_items.append(item_id)
            # The desktop needs only turn counts, never a copy of the words.
            self.emit({"type": "transcript", "role": role,
                       "interrupted": bool(getattr(item, "interrupted", False))})

    def _error(self, event):
        if not self.closing and not self.stop_requested.is_set() and not getattr(event.error, "recoverable", False):
            self.failed = True
            self.stop_requested.set()

    def _registry_activity(self, event):
        self.observed_tools.add(event['tool'])
        self.emit(project_activity(event['tool'], event.get('result'), event['id'], event['phase']))

    def _tools_executed(self, event):
        for call, output in zip(event.function_calls, event.function_call_outputs):
            if call.name in self.observed_tools:
                continue  # Already received directly from the registry, including planner tools.
            activity_id = getattr(call, 'call_id', None) or uuid.uuid4().hex
            self.emit(project_activity(call.name, output.output, activity_id,
                                       'error' if output.is_error else 'result'))

    def _task_progress(self):
        registry = self.components.assistant.registry
        tasks = getattr(registry, 'tasks', None)
        if tasks is not None and (hasattr(tasks, 'progress') or hasattr(tasks, 'presentations')):
            if hasattr(tasks, 'presentations'):
                snapshot = {'type': 'missions', 'missions': [project_task(item) for item in tasks.presentations()]}
            else:
                snapshot = project_task(tasks.presentation() if hasattr(tasks, 'presentation') else tasks.progress())
            if snapshot is not None and snapshot != self.last_task_snapshot:
                self.last_task_snapshot = snapshot
                self.emit(snapshot)

    def _closed(self, event):
        if not self.closing and not self.stop_requested.is_set():
            self.failed = True
            self.stop_requested.set()

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
            setup_step("environment", self.prepare)
            self.components = self.factory()
            c = self.components
            phase = "audio"
            if self.input_choice is not None or self.output_choice is not None:
                c.audio.configure_devices(self.input_choice, self.output_choice)
            if hasattr(c.assistant.registry, "set_activity_observer"):
                c.assistant.registry.set_activity_observer(self._registry_activity)
            c.session.input.audio = c.audio.input
            c.session.output.audio = c.audio.output
            c.session.on("agent_state_changed", self._agent_changed)
            c.session.on("conversation_item_added", self._conversation)
            c.session.on("error", self._error)
            c.session.on("function_tools_executed", self._tools_executed)
            c.session.on("close", self._closed)
            phase = "connection"
            started = await asyncio.wait_for(self._start(), timeout=30)
            if not started or self.stop_requested.is_set():
                return
            phase = "audio"
            c.audio.open(microphone=not self.mute_requested.is_set())  # Never briefly reopen a muted microphone.
            self.ready = True
            sounds = self.sounds_requested.is_set()
            if sounds:
                c.audio.play_cue("ready")
            self.state("muted" if self.mute_requested.is_set() else "listening")
            phase = "session"
            from jarvis.live.prompts import INSIGHT_ANNOUNCEMENT, LIVE_SESSION_GREETING
            c.session.generate_reply(instructions=LIVE_SESSION_GREETING)
            suppressed = False
            next_meter = 0.0
            next_task_poll = 0.0
            next_announcement = 0.0
            while not self.stop_requested.is_set():
                if hasattr(c.audio, 'check_health'):
                    c.audio.check_health()
                if sounds != self.sounds_requested.is_set():
                    sounds = self.sounds_requested.is_set()
                    if not sounds:
                        c.audio.clear_cue()
                now = asyncio.get_running_loop().time()
                if self.cancel_task_requested.is_set():
                    self.cancel_task_requested.clear()
                    tasks = getattr(c.assistant.registry, 'tasks', None)
                    while True:
                        try:
                            task_id = self.task_cancellations.get_nowait()
                        except Empty:
                            break
                        if tasks is not None:
                            tasks.cancel(task_id) if task_id is not None else tasks.cancel()
                if now >= next_task_poll:
                    self._task_progress()
                    next_task_poll = now + 0.25
                if now >= next_meter:
                    incoming, outgoing = c.audio.levels() if hasattr(c.audio, "levels") else (0.0, 0.0)
                    self.emit({"type": "audio_level", "input": incoming, "output": outgoing})
                    next_meter = now + 0.1
                current_suppression = bool(getattr(c.audio, "input_suppressed", False))
                if current_suppression != suppressed:
                    suppressed = current_suppression
                    self.state("muted" if self.mute_requested.is_set() else self.agent_state)
                wanted = not self.mute_requested.is_set()
                if wanted != c.audio.mic_open:
                    c.audio.set_microphone(wanted)
                    if sounds:
                        c.audio.play_cue("ready" if wanted else "muted")
                    self.state(self.agent_state if wanted else "muted")
                if self.agent_state == "listening" and now >= next_announcement:
                    try:
                        queued_at, message = self.announcements.get_nowait()
                    except Empty:
                        pass
                    else:
                        # A stale alert (Jarvis busy talking for minutes) is dropped:
                        # the tray notification already carried it.
                        if monotonic() - queued_at <= ANNOUNCEMENT_MAX_AGE:
                            c.session.generate_reply(
                                instructions=INSIGHT_ANNOUNCEMENT.format(message=message))
                            next_announcement = now + ANNOUNCEMENT_GAP
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
        except (VoiceSetupError, AudioDeviceError) as error:
            error_message = str(error)
        except Exception:
            error_message = {
                "setup": "Le vocal n’a pas pu être préparé. Vérifiez les dépendances et les autorisations macOS.",
                "connection": "Connexion Gemini impossible. Vérifiez la clé, le modèle et l’accès Internet.",
                "audio": "Micro ou sortie audio indisponible. Vérifiez les périphériques et l’autorisation Microphone dans les réglages macOS.",
                "session": "La session vocale a rencontré un problème. Vérifiez la connexion et les périphériques audio.",
            }[phase]
        finally:
            self.closing = True
            self.ready = False
            self.emit({"type": "audio_level", "input": 0.0, "output": 0.0})
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
                    self._task_progress()
                except Exception:
                    error_message = error_message or "Une tâche vocale n’a pas pu être fermée correctement. Vérifiez son résultat avant de réessayer."
                if hasattr(c.assistant.registry, "set_activity_observer"):
                    c.assistant.registry.set_activity_observer(None)
                for close in (c.session.aclose, c.model.aclose):
                    try:
                        await close()
                    except Exception:
                        error_message = error_message or "La session vocale n’a pas pu être fermée correctement. Vérifiez les actions en cours."
            if self.failed and not error_message:
                error_message = "La connexion Gemini s’est interrompue. Vérifiez la clé, le modèle et Internet."
            final = {"type": "state", "state": "error" if error_message else "off",
                     "mic_open": False, "message": error_message or ""}
            if error_message:
                final["retryable"] = phase in {"connection", "session"}
            self.emit(final)

