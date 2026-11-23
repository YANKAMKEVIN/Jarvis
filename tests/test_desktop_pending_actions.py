"""Confirm / Cancel buttons on a prepared outward action (idea 2)."""
import asyncio
import os
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from jarvis.desktop.app import Controller, DesktopShell, STYLE
from jarvis.desktop.live_runtime import LiveRuntime
from jarvis.desktop.presentation import project_pending
from jarvis.live.confirmation import PendingActionStore


def test_store_lists_live_actions_oldest_first_without_content():
    now = [0.0]
    tokens = iter(["t1", "t2"])
    store = PendingActionStore(clock=lambda: now[0], token_factory=lambda: next(tokens), ttl_seconds=10)
    store.register("send_message", lambda: "SECRET BODY")
    now[0] = 1.0
    store.register("open_file", lambda: None)
    assert store.pending() == [("t1", "send_message"), ("t2", "open_file")]
    now[0] = 10.5
    assert store.pending() == [("t2", "open_file")]


def test_projection_keeps_token_and_label_only():
    snapshot = project_pending([("abc", "send_message"), ("def", "unknown_tool"), ("", "send_message")])
    assert snapshot == {"type": "pending_actions", "actions": [
        {"token": "abc", "label": "Envoyer le message préparé"},
        {"token": "def", "label": "Action préparée"}]}


class Tool:
    def __init__(self, name, calls):
        self.info = NS(name=name)
        self.calls = calls

    async def __call__(self, token):
        self.calls.append((self.info.name, token))
        return {"ok": True, "message": "Message envoyé."}


def runtime_with_registry():
    calls = []
    registry = NS(turns=0, pending_actions=PendingActionStore(token_factory=lambda: "tok"))
    registry.note_user_turn = lambda: setattr(registry, "turns", registry.turns + 1)
    events = []
    runtime = LiveRuntime(events.append, prepare=lambda: None)
    runtime.components = NS(assistant=NS(registry=registry, jarvis_tools=[Tool("confirm_action", calls), Tool("cancel_action", calls)]))
    return runtime, registry, calls, events


def test_click_confirm_counts_as_user_turn_then_runs_confirm_action():
    runtime, registry, calls, events = runtime_with_registry()
    asyncio.run(runtime._desktop_action("confirm_pending", {"token": "tok"}))
    assert registry.turns == 1
    assert calls == [("confirm_action", "tok")]
    assert any(e.get("type") == "desktop_result" and e["message"].startswith("Action confirmée") for e in events)


def test_click_cancel_never_notes_a_user_turn():
    runtime, registry, calls, events = runtime_with_registry()
    asyncio.run(runtime._desktop_action("cancel_pending", {"token": "tok"}))
    assert registry.turns == 0
    assert calls == [("cancel_action", "tok")]


def test_resolve_pending_rejects_malformed_tokens():
    runtime = LiveRuntime(lambda event: None, prepare=lambda: None)
    assert runtime.resolve_pending(None, True) is False
    assert runtime.resolve_pending("x" * 65, True) is False
    assert runtime.resolve_pending("tok", True) is True
    assert runtime.desktop_requests.get_nowait() == ("confirm_pending", {"token": "tok"})


def test_pending_snapshot_is_emitted_only_on_change():
    runtime, registry, calls, events = runtime_with_registry()
    registry.pending_actions.register("send_message", lambda: None)
    runtime._pending_progress()
    runtime._pending_progress()
    assert [e for e in events if e["type"] == "pending_actions"] == [
        {"type": "pending_actions", "actions": [{"token": "tok", "label": "Envoyer le message préparé"}]}]


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyleSheet(STYLE)
    return instance


def test_card_buttons_call_the_worker_for_the_shown_action(app, monkeypatch):
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)
    controller = Controller()

    class Settings:
        values = {}
        def value(self, key, default=None): return self.values.get(key, default)
        def setValue(self, key, value): self.values[key] = value

    shell = DesktopShell(app, controller, settings=Settings())

    class Worker:
        def __init__(self): self.calls = []
        def resolve_pending(self, token, confirm):
            self.calls.append((token, confirm))
            return True

    worker = Worker()
    controller.voice_worker = worker
    try:
        shell.show_full()
        panel = shell.full.assistant
        assert not panel.pending_card.isVisibleTo(shell.full)
        controller.voice_event({"type": "pending_actions", "actions": [
            {"token": "a", "label": "Envoyer le message préparé"},
            {"token": "b", "label": "Créer l’événement d’agenda"}]})
        assert panel.pending_card.isVisibleTo(shell.full)
        assert "Envoyer le message préparé" in panel.pending_text.text()
        assert "1 autre action" in panel.pending_text.text()
        assert "a" not in panel.pending_text.text().split()
        panel.pending_confirm.click()
        assert worker.calls == [("a", True)]
        panel.pending_cancel.click()
        assert worker.calls[-1] == ("b", False)
        assert not panel.pending_card.isVisibleTo(shell.full)
        controller.voice_event({"type": "pending_actions", "actions": [{"token": "c", "label": "x"}]})
        controller.voice_event({"type": "state", "state": "off", "mic_open": False})
        assert controller.pending_actions == []
    finally:
        controller.voice_worker = None
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()
