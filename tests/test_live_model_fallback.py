"""Fallback when the Gemini Live preview model disappears (idea 35)."""
import asyncio
from types import SimpleNamespace as NS

import pytest

from jarvis.desktop import live_runtime
from jarvis.desktop.live_runtime import LiveRuntime, choose_live_model
from jarvis.live.config import fallback_live_models, is_unknown_model_error


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    live_runtime.UNAVAILABLE_MODELS.clear()
    monkeypatch.setenv("JARVIS_GEMINI_LIVE_MODEL", "preview-a")
    monkeypatch.setenv("JARVIS_GEMINI_LIVE_FALLBACKS", "stable-b, stable-c")
    yield
    live_runtime.UNAVAILABLE_MODELS.clear()


@pytest.mark.parametrize("text,expected", [
    ("models/gemini-x is not found for API version v1beta, or is not supported for bidiGenerateContent", True),
    ("APIError 404: model not found", True),
    ("Requested entity was not found. model gemini-x", True),
    ("Connection reset by peer", False),
    ("Invalid API key", False),
])
def test_unknown_model_detection(text, expected):
    assert is_unknown_model_error(RuntimeError(text)) is expected


def test_fallback_order_and_env(monkeypatch):
    assert fallback_live_models() == ("stable-b", "stable-c")
    assert choose_live_model() == "preview-a"
    live_runtime.UNAVAILABLE_MODELS.add("preview-a")
    assert choose_live_model() == "stable-b"
    live_runtime.UNAVAILABLE_MODELS.update({"stable-b", "stable-c"})
    assert choose_live_model() == "preview-a"
    monkeypatch.setenv("JARVIS_GEMINI_LIVE_FALLBACKS", "")
    assert fallback_live_models() == ()


class Session:
    def __init__(self): self.input, self.output, self.handlers = NS(audio=None), NS(audio=None), {}
    def on(self, name, callback): self.handlers[name] = callback
    async def start(self, **kwargs): raise RuntimeError("models/preview-a is not found for API version v1beta")
    async def aclose(self): pass


class Closeable:
    async def aclose(self): pass


class Audio:
    input = output = None
    mic_open = False
    def close(self): pass


def test_unknown_model_at_connection_explains_and_next_start_uses_the_fallback():
    requested = []

    def factory(**options):
        requested.append(options.get("model"))
        return NS(session=Session(), audio=Audio(), model=Closeable(), assistant=NS(registry=Closeable()))

    async def scenario(events):
        await LiveRuntime(events.append, factory=factory, prepare=lambda: None).run()

    first, second = [], []
    asyncio.run(scenario(first))
    final = first[-1]
    assert final["state"] == "error" and final["retryable"] is True
    assert "preview-a" in final["message"] and "stable-b" in final["message"]
    asyncio.run(scenario(second))
    assert requested == [None, "stable-b"]
