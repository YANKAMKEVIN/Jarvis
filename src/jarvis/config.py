import os


DEFAULT_LLM_MODEL = "granite4:3b"


def get_llm_model() -> str:
    return os.environ.get("JARVIS_LLM_MODEL", DEFAULT_LLM_MODEL)


SEARXNG_BASE_URL = os.environ.get(
    "SEARXNG_BASE_URL",
    "http://127.0.0.1:8888",
)
SEARXNG_TIMEOUT_SECONDS = float(
    os.environ.get("SEARXNG_TIMEOUT_SECONDS", "5")
)
