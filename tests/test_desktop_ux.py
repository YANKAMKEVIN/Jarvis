"""UI/UX refinements of the desktop window; simulated worker, no model/network/macOS actions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller, DesktopShell, STYLE


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyleSheet(STYLE)
    return instance


class Settings:
    def __init__(self): self.values = {}
    def value(self, key, default=None): return self.values.get(key, default)
    def setValue(self, key, value): self.values[key] = value


@pytest.fixture
def shell(app, monkeypatch):
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)
    controller = Controller()
    controller.reduced_motion = True
    instance = DesktopShell(app, controller, settings=Settings())
    yield instance
    instance.finish_transfer()
    for window in (instance.full, instance.compact, instance.orb_window):
        window.hide()


def listen(controller, state="listening"):
    controller.voice_worker = Mock()
    controller.voice_event({"type": "state", "state": state, "mic_open": True})


def test_voice_shortcuts_follow_the_session_and_pages_have_their_own(shell):
    c, window = shell.controller, shell.full
    assert not window.interrupt_shortcut.isEnabled() and not window.mic_shortcut.isEnabled()
    listen(c, "speaking")
    assert window.interrupt_shortcut.isEnabled() and window.mic_shortcut.isEnabled()
    window.interrupt_shortcut.activated.emit()
    c.voice_worker.interrupt.assert_called_once_with()
    window.mic_shortcut.activated.emit()
    c.voice_worker.set_muted.assert_called_once_with(True)
    assert "Échap" in window.assistant.interrupt_button.text()
    assert window.assistant.mic_button.text().endswith("· M")
    for index, shortcut in enumerate(window.page_shortcuts):
        shortcut.activated.emit()
        assert window.pages.currentIndex() == index
    c.voice_event({"type": "state", "state": "error", "message": "Connexion perdue."})
    assert not window.interrupt_shortcut.isEnabled() and not window.mic_shortcut.isEnabled()
