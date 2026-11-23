"""The text brain, the planner and the self-check share JARVIS_OLLAMA_URL (idea 12)."""
import json

from jarvis.brain import LocalBrain
from jarvis.config import DEFAULT_OLLAMA_URL, get_ollama_url
from jarvis.planner.models import OllamaPlannerModel


def test_default_and_override(monkeypatch):
    monkeypatch.delenv("JARVIS_OLLAMA_URL", raising=False)
    assert get_ollama_url() == DEFAULT_OLLAMA_URL == "http://localhost:11434/api/chat"
    monkeypatch.setenv("JARVIS_OLLAMA_URL", "  ")
    assert get_ollama_url() == DEFAULT_OLLAMA_URL
    monkeypatch.setenv("JARVIS_OLLAMA_URL", "http://mac-mini.local:11500/api/chat")
    assert get_ollama_url() == "http://mac-mini.local:11500/api/chat"
    assert OllamaPlannerModel().url == "http://mac-mini.local:11500/api/chat"


def test_local_brain_posts_to_the_configured_url(monkeypatch):
    monkeypatch.setenv("JARVIS_OLLAMA_URL", "http://10.0.0.5:9999/api/chat")
    seen = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def read(self): return json.dumps({"message": {"content": "ok"}}).encode()

    def urlopen(request, timeout):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr("jarvis.brain.urllib.request.urlopen", urlopen)
    assert LocalBrain().think("bonjour") == "ok"
    assert seen == ["http://10.0.0.5:9999/api/chat"]


def test_self_check_probes_the_configured_host(monkeypatch):
    from jarvis.capabilities import diagnostics
    monkeypatch.setenv("JARVIS_OLLAMA_URL", "http://studio.local:11500/api/chat")
    probed = []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    monkeypatch.setattr("socket.create_connection", lambda address, timeout: probed.append(address) or Connection())
    ok, message = diagnostics._local_model()
    assert ok and probed == [("studio.local", 11500)] and "studio.local:11500" in message
