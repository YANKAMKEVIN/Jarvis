import os
from dataclasses import dataclass


DEFAULT_GEMINI_LIVE_MODEL = "gemini-3.1-flash-live-preview"
DEFAULT_GEMINI_LIVE_VOICE = "Puck"
DEFAULT_LIVE_AGENT_NAME = "jarvis-live-poc"
DEFAULT_GEMINI_LIVE_TEMPERATURE = 0.8

# One-shot multimodal model for Vision (NOT the realtime Live model). An
# explicit, stable GA Flash model id is used rather than a mutable alias such as
# "gemini-flash-latest", so Vision behaviour stays reproducible. Override with
# JARVIS_GEMINI_VISION_MODEL once a preferred available model is confirmed.
DEFAULT_GEMINI_VISION_MODEL = "gemini-3.5-flash"


TEMPERATURE_RANGE = (0.0, 2.0)


def read_float_env(name: str, default: float, low: float, high: float,
                   warnings: list[str] | None = None) -> float:
    """A number from the environment, or `default` with a warning.

    "0,8" is read as 0.8 (French decimal comma). An unreadable or out-of-range
    value never crashes the start: the default is used and the reason is
    reported by the self-check.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip().replace(",", "."))
    except ValueError:
        value = None
    if value is None or value != value or not low <= value <= high:
        if warnings is not None:
            warnings.append(f"{name}={raw.strip()[:20]!r} ignore (nombre entre {low:g} et {high:g} attendu) : {default:g} utilise")
        return default
    return value


def live_config_warnings() -> list[str]:
    """Malformed Live settings, for the self-check (empty when all is well)."""
    warnings: list[str] = []
    read_float_env("JARVIS_GEMINI_LIVE_TEMPERATURE", DEFAULT_GEMINI_LIVE_TEMPERATURE,
                   *TEMPERATURE_RANGE, warnings)
    return warnings


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
        temperature=read_float_env(
            "JARVIS_GEMINI_LIVE_TEMPERATURE",
            DEFAULT_GEMINI_LIVE_TEMPERATURE,
            *TEMPERATURE_RANGE,
        ),
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


def get_vision_model() -> str:
    return os.environ.get(
        "JARVIS_GEMINI_VISION_MODEL",
        DEFAULT_GEMINI_VISION_MODEL,
    )


def is_vision_enabled() -> bool:
    # Opt-in: Vision sends a screen capture to an external service (Gemini), so
    # it stays off until explicitly enabled. Once on, no per-capture prompt.
    return os.environ.get("JARVIS_VISION_ENABLED") == "1"


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
