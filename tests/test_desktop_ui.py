"""Voice-only UI checks; simulated worker, no model/network/macOS actions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QElapsedTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QTextEdit
from jarvis.desktop.app import Controller, DesktopShell, STYLE


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyleSheet(STYLE)
    return instance


def wait_until(app, predicate):
    timer = QElapsedTimer()
    timer.start()
    while not predicate() and timer.elapsed() < 3000:
        app.processEvents()
        QTest.qWait(10)
    assert predicate()


def make_shell(app, monkeypatch, demo=False):
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)
    controller = Controller(demo=demo)
    return controller, DesktopShell(app, controller)


def test_demo_has_no_text_input_and_cannot_activate_voice(app, monkeypatch):
    controller, shell = make_shell(app, monkeypatch, demo=True)
    try:
        shell.show_full()
        for window in (shell.full, shell.compact):
            assert not window.findChildren(QLineEdit)
            assert not window.findChildren(QTextEdit)
            assert not window.assistant.voice_button.isEnabled()
        controller.start_voice()
        assert controller.voice_worker is None and not controller.voice_mic_open
        controller.voice_event({"type": "transcript", "role": "user", "text": "PRIVATE_PHRASE"})
        controller.voice_event({"type": "transcript", "role": "assistant", "text": "PRIVATE_REPLY"})
        assert controller.voice_turns == 1
        assert not hasattr(controller, "session")
        assert "PRIVATE" not in str(vars(controller))
        for window in (shell.full, shell.compact):
            assert all("PRIVATE" not in widget.text() for widget in window.findChildren(QLabel))
        controller.reduced_motion = True
        controller.changed.emit()
        assert not shell.full.assistant.orb.timer.isActive()
        shell.switch_view()
        assert shell.compact.isVisible() and not shell.full.isVisible()
        assert not shell.compact.assistant.orb.timer.isActive()
    finally:
        shell.full.hide()
        shell.compact.hide()


def test_voice_controls_share_one_worker_and_cleanup_before_quit(app, monkeypatch):
    from threading import Event
    from PySide6.QtCore import QThread, Signal
    from jarvis.desktop import live_worker

    class SimulatedVoiceWorker(QThread):
        event = Signal(object)
        def __init__(self, parent=None):
            super().__init__(parent)
            self.stop_flag = Event()
            self.muted = False
            self.interrupts = 0
        def run(self):
            self.event.emit({"type": "state", "state": "listening", "mic_open": True})
            self.event.emit({"type": "transcript", "role": "user"})
            self.stop_flag.wait(3)
            self.event.emit({"type": "state", "state": "off", "mic_open": False})
        def stop(self): self.stop_flag.set()
        def set_muted(self, muted):
            self.muted = muted
            self.event.emit({"type": "state", "state": "muted" if muted else "listening", "mic_open": not muted})
        def interrupt(self): self.interrupts += 1

    monkeypatch.setattr("jarvis.desktop.live_runtime.preload_live_plugins", lambda: None)
    monkeypatch.setattr(live_worker, "LiveWorker", SimulatedVoiceWorker)
    controller, shell = make_shell(app, monkeypatch)
    ready = []
    controller.exit_ready.connect(lambda: ready.append(True))
    try:
        shell.show_full()
        assert controller.voice_worker is None
        shell.full.assistant.voice_button.click()
        wait_until(app, lambda: controller.voice_mic_open and controller.voice_turns == 1)
        worker = controller.voice_worker
        controller.start_voice()
        assert controller.voice_worker is worker
        shell.show_compact()
        assert shell.compact.assistant.mic_button.isVisible()
        controller.voice_event({"type": "state", "state": "speaking", "mic_open": True,
                                "input_suppressed": True})
        assert "pause" in shell.compact.assistant.voice_notice.text()
        assert "pause" in shell.full.assistant.voice_notice.text()
        controller.voice_event({"type": "state", "state": "listening", "mic_open": True,
                                "input_suppressed": True})
        assert "Reprise" in shell.compact.assistant.status.text()
        shell.compact.assistant.mic_button.click()
        wait_until(app, lambda: not controller.voice_mic_open)
        assert worker.muted
        shell.compact.assistant.mic_button.click()
        wait_until(app, lambda: controller.voice_mic_open)
        assert not worker.muted
        shell.compact.assistant.interrupt_button.click()
        assert worker.interrupts == 1
        shell.quit()
        assert controller.quit_after_voice
        wait_until(app, lambda: controller.voice_worker is None)
        assert ready and not controller.voice_mic_open
    finally:
        if controller.voice_worker:
            controller.stop_voice()
            wait_until(app, lambda: controller.voice_worker is None)
        shell.full.hide()
        shell.compact.hide()
