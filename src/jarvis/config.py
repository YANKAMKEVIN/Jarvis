import os


DEFAULT_LLM_MODEL = "granite4:3b"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"


def get_llm_model() -> str:
    return os.environ.get("JARVIS_LLM_MODEL", DEFAULT_LLM_MODEL)


def get_ollama_url() -> str:
    """Ollama chat endpoint shared by the text brain and the planner.

    JARVIS_OLLAMA_URL points to another machine or port (full /api/chat URL).
    """
    return os.environ.get("JARVIS_OLLAMA_URL", "").strip() or DEFAULT_OLLAMA_URL


SEARXNG_BASE_URL = os.environ.get(
    "SEARXNG_BASE_URL",
    "http://127.0.0.1:8888",
)
def _timeout_seconds(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "").strip().replace(",", ".") or default)
    except ValueError:
        return default
    return value if 0 < value <= 120 else default


SEARXNG_TIMEOUT_SECONDS = _timeout_seconds("SEARXNG_TIMEOUT_SECONDS", 5.0)
