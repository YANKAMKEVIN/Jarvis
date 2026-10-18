"""Voice-only UI checks; simulated worker, no model/network/macOS actions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QElapsedTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QTextEdit
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
    class Settings:
        def __init__(self): self.values = {}
        def value(self, key, default=None): return self.values.get(key, default)
        def setValue(self, key, value): self.values[key] = value
    return controller, DesktopShell(app, controller, settings=Settings())


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


def test_audio_changes_orb_without_rebuilding_controls_and_motion_can_stop(app, monkeypatch):
    controller, shell = make_shell(app, monkeypatch, demo=True)
    try:
        shell.show_full()
        controller.voice_event({'type': 'audio_level', 'input': 0.25, 'output': 0.0})
        assert shell.full.assistant.orb.target > 0
        assert shell.full.assistant.orb.target == shell.compact.assistant.orb.target
        shell.full.assistant.orb.tick()
        assert shell.full.assistant.orb.energy > 0
        controller.reduced_motion = True
        controller.changed.emit()
        assert not shell.full.assistant.orb.timer.isActive()
        assert shell.full.assistant.orb.energy == 0
        assert shell.full.assistant.controls.fade.state().name == 'Stopped'
        controller.voice_event({'type': 'audio_level', 'input': 0.0, 'output': 0.0})
        assert shell.full.assistant.orb.target == 0
        controller.voice_event({'type': 'tool_receipt', 'label': 'Rappel', 'status': 'confirmation'})
        assert 'Accord vocal attendu' in shell.compact.assistant.hint.text()
        assert shell.compact.assistant.hint.text() == shell.full.assistant.hint.text()
        controller.clear_tool_notice()
        assert 'Accord vocal' not in shell.full.assistant.hint.text()
    finally:
        shell.finish_transfer()
        shell.full.hide()
        shell.compact.hide()


def test_transfer_cleans_up_on_rapid_switch_and_reduced_motion(app, monkeypatch):
    controller, shell = make_shell(app, monkeypatch, demo=True)
    try:
        shell.show_full()
        shell.show_compact()
        assert shell.transfer is not None
        shell.show_full()  # Cancel in-flight animation, don't leave an invisible orb.
        assert shell.transfer is not None
        controller.reduced_motion = True
        controller.changed.emit()
        assert shell.transfer is None
        assert shell.full.assistant.orb.graphicsEffect() is None
        assert shell.compact.assistant.orb.graphicsEffect() is None
        shell.show_compact()
        assert shell.transfer is None
        assert shell.compact.isVisible()
        image = shell.compact.grab().toImage()
        assert image.pixelColor(0, 0).alpha() == 0
        shell.show_full()
        shell.full.navigate(2)
        controller.reduced_motion = False
        controller.changed.emit()
        shell.show_compact()
        assert shell.transfer is None  # No ghost orb from the Settings page.
        shell.show_full()
        assert shell.full.pages.currentIndex() == 0
        wait_until(app, lambda: shell.transfer is None)
        assert shell.full.assistant.orb.graphicsEffect() is None
    finally:
        shell.finish_transfer()
        shell.full.hide()
        shell.compact.hide()


def test_companion_remembers_position_and_recovers_from_missing_monitor(app, monkeypatch, tmp_path):
    from PySide6.QtCore import QPoint, QSettings
    from PySide6.QtGui import QGuiApplication
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable', lambda: False)
    settings = QSettings(str(tmp_path / 'desktop.ini'), QSettings.Format.IniFormat)
    settings.setValue('companion/position', QPoint(99999, 99999))
    controller = Controller()
    controller.reduced_motion = True
    shell = DesktopShell(app, controller, settings=settings)
    try:
        shell.show_compact()
        area = QGuiApplication.primaryScreen().availableGeometry()
        assert area.contains(shell.compact.geometry())
        position = area.topLeft() + QPoint(25, 25)
        shell.compact.move(position)
        shell.show_full()
        assert settings.value('companion/position') == position
        shell.position_restored = False
        shell.show_compact()
        assert shell.compact.pos() == position
    finally:
        shell.finish_transfer()
        shell.full.hide()
        shell.compact.hide()


def test_three_modes_share_session_and_orb_click_never_opens_micro(app, monkeypatch):
    from PySide6.QtCore import QPoint, Qt
    controller, shell = make_shell(app, monkeypatch, demo=True)
    try:
        controller.reduced_motion = True
        shell.show_orb()
        assert shell.orb_window.isVisible() and not shell.full.isVisible() and not shell.compact.isVisible()
        first = shell.orb_window.grab().toImage()
        second = shell.orb_window.grab().toImage()
        assert first == second  # Transparent repaint must not accumulate glow.
        assert not controller.voice_mic_open and controller.voice_worker is None
        QTest.mouseClick(shell.orb_window.orb, Qt.MouseButton.LeftButton, pos=QPoint(90, 90))
        assert shell.compact.isVisible() and not shell.orb_window.isVisible()
        assert controller.voice_worker is None
        controller.voice_event({'type': 'audio_level', 'input': 0.16, 'output': 0.0})
        assert shell.orb_window.orb.target == shell.compact.assistant.orb.target
        shell.show_orb()
        shell.show_full()
        assert shell.full.isVisible() and not shell.orb_window.isVisible()
        assert not shell.orb_window.orb.timer.isActive()
    finally:
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_cards_and_actions_are_shared_bounded_and_confirmation_stays_vocal(app, monkeypatch):
    from jarvis.desktop.presentation import project_activity
    controller, shell = make_shell(app, monkeypatch, demo=True)
    try:
        controller.reduced_motion = True
        shell.show_compact()
        controller.voice_event(project_activity('list_calendar_events', {'ok': True,
            'events': [{'title': '<b>Réunion</b>', 'start': '10:00', 'token': 'PRIVATE_TOKEN'}]}, 'calendar'))
        assert len(controller.cards) == 1
        assert shell.compact.assistant.hint_area.currentIndex() == 1
        shell.compact.assistant.details_button.click()
        assert shell.full.isVisible() and shell.full.pages.currentIndex() == 1
        labels = shell.full.cards_page.findChildren(QLabel)
        meeting = next(w for w in labels if '<b>Réunion</b>' in w.text())
        assert meeting.textFormat().name == 'PlainText'
        assert all('PRIVATE' not in w.text() for w in labels)
        controller.voice_event(project_activity('prepare_send_message',
            {'ok': False, 'requires_confirmation': True, 'token': 'PRIVATE_TOKEN'}, 'message'))
        shell.full.navigate(2)
        assert any('Accord vocal attendu' in w.text() for w in shell.full.activity.findChildren(QLabel))
        assert not any(b.text() == 'Confirmer' for b in shell.full.findChildren(QPushButton))
        for i in range(50):
            controller.voice_event(project_activity('open_app', {'ok': True}, str(i)))
        assert len(controller.activity) == 30
        controller.clear_cards()
        assert not controller.cards
        assert not shell.full.assistant.peek.isVisibleTo(shell.full)
    finally:
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_task_cancel_button_waits_for_actual_outcome_and_never_confirms_actions(app, monkeypatch):
    controller, shell = make_shell(app, monkeypatch)
    class Worker:
        cancellations = 0
        def cancel_task(self): self.cancellations += 1
    worker = Worker()
    controller.voice_worker = worker
    try:
        shell.show_full()
        controller.voice_event({'type': 'task_progress', 'id': 'task', 'status': 'running',
                                'steps': [], 'step_count': 0})
        shell.full.navigate(2)
        app.processEvents()
        cancel = shell.full.activity.findChild(QPushButton, 'cancelTask')
        assert cancel.isEnabled()
        cancel.click()
        assert worker.cancellations == 1
        assert controller.task['status'] == 'running'  # Sending a request is not completion.
        controller.voice_event({'type': 'task_progress', 'id': 'task', 'status': 'cancelling',
                                'steps': [], 'step_count': 0})
        app.processEvents()
        cancel = shell.full.activity.findChild(QPushButton, 'cancelTask')
        assert not cancel.isEnabled()
        controller.voice_event({'type': 'task_progress', 'id': 'task', 'status': 'cancelled',
                                'steps': [], 'step_count': 0})
        app.processEvents()
        assert shell.full.activity.findChild(QPushButton, 'cancelTask') is None
        assert any('Tâche annulée' in w.text() for w in shell.full.activity.findChildren(QLabel))
    finally:
        controller.voice_worker = None
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_dragging_orb_moves_it_without_opening_companion(app, monkeypatch):
    from PySide6.QtCore import QPoint, Qt
    controller, shell = make_shell(app, monkeypatch, demo=True)
    try:
        controller.reduced_motion = True
        shell.show_orb()
        origin = shell.orb_window.pos()
        orb = shell.orb_window.orb
        QTest.mousePress(orb, Qt.MouseButton.LeftButton, pos=QPoint(80, 80))
        QTest.mouseMove(orb, QPoint(115, 100))
        QTest.mouseRelease(orb, Qt.MouseButton.LeftButton, pos=QPoint(115, 100))
        assert shell.orb_window.pos() != origin
        assert shell.orb_window.isVisible() and not shell.compact.isVisible()
        assert controller.voice_worker is None
    finally:
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()
