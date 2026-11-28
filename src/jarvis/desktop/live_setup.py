"""Voice session setup: environment, LiveKit plugins, turn detection, greeting and components."""
from __future__ import annotations

import asyncio
import os
import traceback
from pathlib import Path
from types import SimpleNamespace


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
             "agent_session": "session LiveKit", "wake_word": "mot d’éveil local"}
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
               "JARVIS_PLANNER_NUM_CTX", "JARVIS_PLANNER_TIMEOUT", "JARVIS_LLM_MODEL",
               "JARVIS_ECHO_CANCEL"}
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


DEFAULT_TURN_SILENCE_MS = 1100


def turn_silence_ms():
    """Silence that ends a turn; JARVIS_TURN_SILENCE_MS tunes it in the field."""
    try:
        value = int(os.environ.get("JARVIS_TURN_SILENCE_MS", DEFAULT_TURN_SILENCE_MS))
    except ValueError:
        return DEFAULT_TURN_SILENCE_MS
    return min(max(value, 400), 3000)


def desktop_turn_detection_config():
    """Let the user pause to think mid-sentence without Jarvis taking the turn."""
    from google.genai import types
    return types.RealtimeInputConfig(automatic_activity_detection=types.AutomaticActivityDetection(
        disabled=False,
        start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
        prefix_padding_ms=300,
        silence_duration_ms=turn_silence_ms(),
    ))


def introduced_marker_path():
    return Path(os.environ.get("JARVIS_INTRODUCED_PATH")
                or Path.home() / "Library/Application Support/Jarvis/introduced")


def session_greeting():
    """Introduce Jarvis once ever; afterwards only a short welcome back."""
    from jarvis.live.prompts import LIVE_SESSION_GREETING, LIVE_SESSION_WELCOME_BACK
    marker = introduced_marker_path()
    if marker.exists():
        return LIVE_SESSION_WELCOME_BACK
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass  # Worst case Jarvis introduces itself again next launch.
    return LIVE_SESSION_GREETING


def long_session_options():
    """Wake-word sessions idle for hours: let Gemini slide its context window
    and resume across server GoAway resets instead of hitting the 15 min cap."""
    from google.genai import types
    return {"context_window_compression": types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()),
            "session_resumption": types.SessionResumptionConfig()}


def create_components(voice=None, long_session=False):
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
        if voice is not None:
            from dataclasses import replace
            config = replace(config, voice=voice)
    except (ValueError, TypeError):
        raise VoiceSetupError("Configuration Gemini invalide. Vérifiez le modèle, la voix et la température.") from None
    audio = setup_step("audio_import", lambda: LocalAudio(asyncio.get_running_loop()))
    assistant = setup_step("macos_tools", lambda: create_assistant_class(Agent, desktop=True)())
    model = setup_step("gemini_model", lambda: create_realtime_model(google, config,
        realtime_input_config=desktop_turn_detection_config(),
        **(long_session_options() if long_session else {})))
    # Gemini handles turn detection. No inference service or LiveKit room/token.
    session = setup_step("agent_session", lambda: AgentSession(llm=model, vad=None, turn_handling={
        "turn_detection": "realtime_llm",
        "interruption": {"resume_false_interruption": False},
    }))
    return SimpleNamespace(model=model, session=session,
        assistant=assistant, audio=audio)
