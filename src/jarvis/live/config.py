import os
from dataclasses import dataclass


DEFAULT_GEMINI_LIVE_MODEL = "gemini-3.1-flash-live-preview"
DEFAULT_GEMINI_LIVE_VOICE = "Puck"
DEFAULT_LIVE_AGENT_NAME = "jarvis-live-poc"
DEFAULT_GEMINI_LIVE_TEMPERATURE = 0.8


@dataclass(frozen=True)
class LiveConfig:
    model: str
    voice: str
    temperature: float
    agent_name: str


def get_live_config() -> LiveConfig:
    return LiveConfig(
        model=os.environ.get(
            "JARVIS_GEMINI_LIVE_MODEL",
            DEFAULT_GEMINI_LIVE_MODEL,
        ),
        voice=os.environ.get(
            "JARVIS_GEMINI_LIVE_VOICE",
            DEFAULT_GEMINI_LIVE_VOICE,
        ),
        temperature=float(os.environ.get(
            "JARVIS_GEMINI_LIVE_TEMPERATURE",
            str(DEFAULT_GEMINI_LIVE_TEMPERATURE),
        )),
        agent_name=os.environ.get(
            "JARVIS_LIVE_AGENT_NAME",
            DEFAULT_LIVE_AGENT_NAME,
        ),
    )


def get_required_runtime_env_names() -> tuple[str, ...]:
    return (
        "GOOGLE_API_KEY",
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
    )


def is_live_debug_enabled() -> bool:
    return os.environ.get("JARVIS_DEBUG_LIVE") == "1"


def debug_live(event: str, **fields) -> None:
    if not is_live_debug_enabled():
        return

    print("============== JARVIS LIVE DEBUG ==============")
    print(f"EVENT: {event}")

    for key, value in fields.items():
        print(f"{key}: {value}")

    print("===============================================")
