"""Typed messages to the Live session from the Assistant window (idea 3)."""
import os
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from jarvis.desktop.app import Controller, DesktopShell, STYLE
from jarvis.desktop.live_runtime import LiveRuntime, MAX_TYPED_CHARS
from jarvis.live.confirmation import ConfirmationNeedsUserTurn, PendingActionStore


class Session:
    def __init__(self): self.replies = []
    def generate_reply(self, **kwargs): self.replies.append(kwargs)


def test_runtime_rejects_empty_or_oversized_text():
    runtime = LiveRuntime(lambda event: None, prepare=lambda: None)
    assert runtime.send_text("   ") is False
    assert runtime.send_text(None) is False
    assert runtime.send_text("x" * (MAX_TYPED_CHARS + 1)) is False
    assert runtime.send_text("  Bonjour  ") is True
    assert runtime.typed_messages.get_nowait() == "Bonjour"


def test_typed_text_goes_to_generate_reply_and_counts_as_user_turn():
    events = []
    store = PendingActionStore(token_factory=lambda: "tok")
    registry = NS(note_user_turn=store.note_user_turn)
    runtime = LiveRuntime(events.append, prepare=lambda: None)
    runtime.components = NS(assistant=NS(registry=registry))
    session = Session()
    store.register("send_message", lambda: None)
    with pytest.raises(ConfirmationNeedsUserTurn):
        store.confirm("tok")
    runtime.send_text("oui, envoie")
    assert runtime._deliver_typed(session) is True
    assert session.replies == [{"user_input": "oui, envoie"}]
    assert store.confirm("tok") is not None
    assert {"type": "request_progress", "stage": "received", "message": "Demande reçue"} in events
    assert runtime._deliver_typed(session) is False


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyleSheet(STYLE)
    return instance


def test_text_field_sends_to_worker_only_with_an_active_session(app, monkeypatch):
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)
    controller = Controller()

    class Settings:
        values = {}
        def value(self, key, default=None): return self.values.get(key, default)
        def setValue(self, key, value): self.values[key] = value

    shell = DesktopShell(app, controller, settings=Settings())

    class Worker:
        def __init__(self): self.sent = []
        def send_text(self, text):
            self.sent.append(text)
            return True

    try:
        shell.show_full()
        field = shell.full.assistant.text_input
        assert isinstance(field, QLineEdit) and not field.isVisibleTo(shell.full)
        assert controller.send_text("Bonjour") is False
        worker = Worker()
        controller.voice_worker = worker
        controller.voice_state = "listening"
        controller.changed.emit()
        assert field.isVisibleTo(shell.full) and field.isEnabled()
        field.setText("  Quelle heure est-il ?  ")
        field.returnPressed.emit()
        assert worker.sent == ["Quelle heure est-il ?"]
        assert field.text() == ""
        field.returnPressed.emit()
        assert worker.sent == ["Quelle heure est-il ?"]
    finally:
        controller.voice_worker = None
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()
