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


def test_multiple_mission_cards_cancel_by_id_and_compact_cycles_all_missions(app, monkeypatch):
    import sys
    from unittest.mock import Mock
    from jarvis.desktop.presentation import project_task
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *args: errors.append(args))
    c, shell = make_shell(app, monkeypatch)
    c.reduced_motion = True
    c.voice_worker = Mock()
    c.voice_state = 'listening'
    try:
        shell.show_full()
        missions = [project_task({'id': str(i), 'objective': 'Objectif ' + str(i),
            'status': 'running' if i < 2 else 'queued', 'current_tool': 'web_answer' if i < 2 else None, 'steps': []}) for i in range(3)]
        c.voice_event({'type': 'missions', 'missions': missions})
        app.processEvents()
        deck = shell.full.assistant.mission
        assert len([p for p in deck.panels if p.isVisible()]) == 2
        assert '3 missions actives' in deck.count.text() and '1 autres' in deck.count.text()
        c.cancel_task()
        c.voice_worker.cancel_task.assert_not_called()
        deck.panels[1].cancel.click()
        c.voice_worker.cancel_task.assert_called_once_with('1')
        shell.show_compact()
        compact = shell.compact.assistant.mission
        seen = set()
        for _ in range(3):
            seen.add(c.selected_mission_id)
            compact.count.click()
        assert seen == {'0', '1', '2'}
        compact.summary.click()
        assert shell.full.pages.currentIndex() == 2
        c.voice_event({'type': 'state', 'state': 'error'})
        assert all(m['status'] == 'unknown' for m in c.missions.values())
        assert not errors
    finally:
        c.voice_worker = None
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_multi_mission_snapshots_keep_other_running_mission_visible_after_completion(app, monkeypatch):
    from jarvis.desktop.presentation import project_task
    c, shell = make_shell(app, monkeypatch)
    c.reduced_motion = True
    def snapshot(a, b):
        c.voice_event({'type': 'missions', 'missions': [project_task({'id': identifier,
            'objective': identifier, 'status': state, 'steps': []}) for identifier, state in [('a', a), ('b', b)]]})
    try:
        shell.show_full()
        snapshot('running', 'queued')
        assert c.task['id'] == 'a'
        snapshot('completed', 'running')
        assert c.task['id'] == 'b' and c.task['status'] == 'running'
        assert shell.full.assistant.mission.panels[0].bound_task['id'] == 'b'
        c.clear_activity()
        assert c.missions
        snapshot('completed', 'cancelled')
        assert c.task['status'] == 'cancelled'
        assert not shell.full.assistant.mission.expanded
        c.clear_activity()
        assert not c.missions and c.task is None
    finally:
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_two_mission_cards_fit_small_window(app, monkeypatch):
    from jarvis.desktop.presentation import project_task
    c, shell = make_shell(app, monkeypatch)
    c.reduced_motion = True
    try:
        shell.full.resize(800, 730)
        shell.show_full()
        c.voice_event({'type': 'missions', 'missions': [project_task({'id': str(i),
            'objective': 'Un objectif très détaillé ' * 20, 'status': 'running',
            'current_tool': 'web_answer', 'steps': [{'tool': 'web_answer', 'ok': True}] * 3}) for i in range(2)]})
        panel = shell.full.assistant
        wait_until(app, lambda: panel.mission.geometry().right() < panel.width())
        assert shell.full.width() == 800
        assert panel.controls.geometry().bottom() < panel.height()
        assert all(p.cancel.isVisible() for p in panel.mission.panels)
    finally:
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_assistant_mission_is_beside_orb_then_becomes_dismissible_bilan(app, monkeypatch):
    from PySide6.QtCore import QPoint
    from jarvis.desktop.presentation import project_task
    c, shell = make_shell(app, monkeypatch)
    c.reduced_motion = True
    try:
        shell.show_full()
        panel = shell.full.assistant
        assert panel.mission.isHidden()
        c.voice_event(project_task({'id': 'mission', 'objective': 'Préparer ma journée',
            'status': 'running', 'current_tool': 'list_calendar_events',
            'steps': [{'tool': 'list_files', 'ok': True}]}))
        app.processEvents()
        assert panel.mission.isVisible()
        assert panel.mission.mapToGlobal(QPoint()).x() > panel.orb.mapToGlobal(QPoint()).x() + panel.orb.width()
        assert panel.mission.current.text() == 'En cours · Agenda'
        assert not panel.mission.dismiss.isVisible()
        c.voice_event(project_task({'id': 'mission', 'objective': 'Préparer ma journée',
            'status': 'completed', 'steps': []}))
        app.processEvents()
        assert not panel.mission.expanded and panel.mission.dismiss.isVisible()
        assert not panel.mission.cancel.isVisible()
        panel.mission.dismiss.click()
        assert panel.mission.isHidden() and c.task is not None
        assert shell.compact.assistant.mission.isHidden()
        assert panel.orb.width() == 360
        c.voice_event(project_task({'id': 'next', 'status': 'needs_confirmation', 'steps': []}))
        assert not panel.mission.isHidden() and panel.mission.expanded
        assert 'accord' in panel.mission.state.text()
        assert not panel.mission.cancel.isVisible()
    finally:
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_compact_mission_opens_activity_even_when_cards_exist(app, monkeypatch):
    from jarvis.desktop.presentation import project_activity, project_task
    c, shell = make_shell(app, monkeypatch)
    c.reduced_motion = True
    try:
        c.voice_event(project_activity('get_volume', {'ok': True, 'volume': 30}, 'volume'))
        c.voice_event(project_task({'id': 'mission', 'objective': 'Mon objectif', 'status': 'running', 'current_tool': 'open_app', 'steps': []}))
        shell.show_compact()
        app.processEvents()
        panel = shell.compact.assistant.mission
        assert panel.isVisible() and panel.summary.isVisible()
        assert panel.summary.text() == 'Mon objectif\nEn cours · Application'
        assert panel.cancel.isHidden()
        panel.summary.click()
        assert shell.full.isVisible() and shell.full.pages.currentIndex() == 2
    finally:
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_mission_cancel_uses_existing_controller_and_reduced_motion_stops_fade(app, monkeypatch):
    from unittest.mock import Mock
    from jarvis.desktop.presentation import project_task
    c, shell = make_shell(app, monkeypatch)
    try:
        c.voice_worker = Mock()
        c.voice_state = 'listening'
        c.voice_event(project_task({'id': 'mission', 'status': 'running', 'steps': []}))
        panel = shell.full.assistant.mission
        assert panel.cancel.isEnabled()
        panel.cancel.click()
        c.voice_worker.cancel_task.assert_called_once_with()
        c.voice_worker.interrupt.assert_not_called()
        c.reduced_motion = True
        c.changed.emit()
        assert panel.opacity.opacity() == 1 and panel.fade.state() == panel.fade.State.Stopped
        c.voice_state = 'error'
        c.changed.emit()
        assert not panel.cancel.isEnabled()
    finally:
        c.voice_worker = None
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_mission_layout_fits_small_window_with_long_objective(app, monkeypatch):
    from jarvis.desktop.presentation import project_task
    c, shell = make_shell(app, monkeypatch)
    c.reduced_motion = True
    try:
        shell.full.resize(800, 730)
        shell.show_full()
        c.voice_event(project_task({'id': 'mission', 'objective': 'Un objectif très détaillé ' * 20,
            'status': 'running', 'current_tool': 'open_app',
            'steps': [{'tool': 'open_app', 'ok': True}] * 8}))
        app.processEvents()
        panel = shell.full.assistant
        wait_until(app, lambda: panel.mission.geometry().right() < panel.width())
        assert shell.full.width() == 800
        assert panel.mission.geometry().right() < panel.width()
        assert panel.controls.geometry().bottom() < panel.height()
        assert panel.mission.cancel.isVisible()
        assert len([w for w in panel.mission.steps if w.isVisible()]) == 3
    finally:
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_screen_indicator_follows_overlapping_operations_and_session_end(app, monkeypatch):
    from jarvis.desktop.presentation import project_activity
    from jarvis.desktop.tray import presence
    c, shell = make_shell(app, monkeypatch)
    try:
        c.voice_state = 'thinking'
        c.voice_event(project_activity('describe_screen', None, 'a', 'started'))
        c.voice_event(project_activity('capture_window', None, 'b', 'started'))
        assert len(c.screen_operations) == 2
        assert shell.full.assistant.status.text() == 'Observation d’écran en cours'
        assert 'Observation' in shell.orb_window.status.text()
        assert presence(c)[0] == 'Observation d’écran en cours'
        c.voice_event(project_activity('describe_screen', {'ok': False}, 'a'))
        assert c.screen_operations == {'b'}
        c.voice_event(project_activity('capture_window', None, 'b', 'cancelled'))
        assert not c.screen_operations
        c.voice_event(project_activity('ask_about_screen', None, 'c', 'started'))
        c.voice_event({'type': 'state', 'state': 'error', 'retryable': True})
        assert not c.screen_operations
        assert shell.full.assistant.status.text() == 'Vocal indisponible'
    finally:
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_missions_keep_bounded_session_bilans_and_clear_only_when_idle(app, monkeypatch):
    from jarvis.desktop.presentation import project_task
    c, shell = make_shell(app, monkeypatch)
    try:
        for i in range(7):
            c.voice_event(project_task({'id': str(i), 'status': 'completed',
                'objective': '<b>Mission</b> ' + str(i), 'steps': [{'tool': 'open_app', 'ok': True}]}))
        assert len(c.mission_history) == 4
        texts = [w.text() for w in shell.full.findChildren(QLabel)]
        assert '<b>Mission</b> 6' in texts
        c.voice_event(project_task({'id': 'current', 'status': 'running',
            'objective': 'Objectif en cours', 'current_tool': 'open_app', 'steps': []}))
        c.clear_activity()
        assert c.task['id'] == 'current' and len(c.mission_history) == 4
        assert any(w.text() == 'En cours · Application' for w in shell.full.findChildren(QLabel))
        c.voice_event({'type': 'state', 'state': 'error'})
        assert c.task['status'] == 'unknown'
        c.clear_activity()
        assert c.task is None and not c.mission_history
    finally:
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_screen_card_and_mission_render_without_swallowed_qt_slot_errors(app, monkeypatch):
    import sys
    from jarvis.desktop.presentation import project_activity, project_task
    errors = []
    monkeypatch.setattr(sys, 'excepthook', lambda *args: errors.append(args))
    c, shell = make_shell(app, monkeypatch)
    try:
        c.voice_event(project_activity('ask_about_screen', {'ok': True,
            'analysis': '<b>Résultat lisible</b>', 'source': 'window', 'image_path': 'PRIVATE_PATH'}, 'screen'))
        c.voice_event(project_task({'id': 'a', 'status': 'completed', 'objective': 'Comprendre l’erreur', 'steps': []}))
        panel = shell.full.pages.widget(1)
        assert panel.clear.isEnabled()
        labels = panel.findChildren(QLabel)
        assert any(w.text() == '<b>Résultat lisible</b>' for w in labels)
        assert all('PRIVATE' not in w.text() for w in labels)
        c.clear_cards()
        assert not panel.clear.isEnabled()
        assert not errors
    finally:
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


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


def test_reconnect_preserves_review_history_and_mute_but_never_starts_twice(app, monkeypatch):
    from threading import Event
    from PySide6.QtCore import QThread, Signal
    from jarvis.desktop import live_worker
    created = []
    class Worker(QThread):
        event = Signal(object)
        def __init__(self, parent=None):
            super().__init__(parent)
            self.closed = Event()
            self.muted = False
            self.devices = None
            created.append(self)
        def set_muted(self, value): self.muted = value
        def set_devices(self, a, b): self.devices = (a, b)
        def run(self):
            self.event.emit({'type': 'state', 'state': 'muted' if self.muted else 'listening', 'mic_open': not self.muted})
            self.closed.wait(3)
            self.event.emit({'type': 'state', 'state': 'error', 'mic_open': False,
                             'retryable': True, 'message': 'Connexion coupée'})
        def stop(self): self.closed.set()
    monkeypatch.setattr('jarvis.desktop.live_runtime.preload_live_plugins', lambda: None)
    monkeypatch.setattr(live_worker, 'LiveWorker', Worker)
    controller, shell = make_shell(app, monkeypatch)
    try:
        controller.reduced_motion = True
        shell.show_full()
        controller.start_voice()
        wait_until(app, lambda: controller.voice_mic_open)
        controller.toggle_microphone()
        assert controller.microphone_muted
        controller.voice_event({'type': 'activity', 'id': 'old-action', 'label': 'Application', 'status': 'verified', 'card': None})
        created[0].closed.set()
        wait_until(app, lambda: controller.voice_worker is None)
        assert controller.can_reconnect and shell.full.assistant.voice_button.text() == 'Reconnecter'
        shell.full.assistant.voice_button.click()
        controller.start_voice()
        wait_until(app, lambda: controller.voice_state == 'muted')
        assert len(created) == 2 and created[1].muted
        assert 'old-action' in controller.activity
        assert not controller.voice_mic_open
    finally:
        controller.stop_voice()
        wait_until(app, lambda: controller.voice_worker is None)
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_audio_job_is_exclusive_and_quit_waits_for_cleanup(app, monkeypatch):
    from threading import Event
    from PySide6.QtCore import QThread, Signal, QEvent
    from jarvis.desktop import audio_settings
    class Job(QThread):
        event = Signal(object)
        def __init__(self, kind, a, b, parent=None):
            super().__init__(parent)
            self.closed = Event()
        def run(self): self.closed.wait(3)
        def stop(self): self.closed.set()
    monkeypatch.setattr(audio_settings, 'AudioJob', Job)
    controller, shell = make_shell(app, monkeypatch)
    ready = []
    controller.exit_ready.connect(lambda: ready.append(True))
    try:
        controller.start_audio_job('microphone')
        job = controller.audio_worker
        assert job is not None
        controller.handle_audio_event({'type': 'audio_test', 'state': 'microphone', 'message': 'Test local'})
        assert controller.local_mic_open
        shell.show_orb()
        assert 'Test micro local' in shell.orb_window.status.text()
        controller.start_audio_job('speaker')
        controller.start_voice()
        assert controller.audio_worker is job and controller.voice_worker is None
        assert shell.quit_guard.eventFilter(app, QEvent(QEvent.Type.Quit))
        wait_until(app, lambda: controller.audio_worker is None)
        assert ready and job.closed.is_set()
        assert not controller.local_mic_open
    finally:
        if controller.audio_worker:
            controller.stop_audio_job()
            wait_until(app, lambda: controller.audio_worker is None)
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()


def test_device_preferences_are_saved_and_invalid_preferences_block_capture(app, monkeypatch, tmp_path):
    import json
    from PySide6.QtCore import QSettings
    settings = QSettings(str(tmp_path / 'devices.ini'), QSettings.Format.IniFormat)
    settings.setValue('audio/input_device', 'broken-json')
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable', lambda: False)
    controller = Controller()
    shell = DesktopShell(app, controller, settings=settings)
    try:
        assert controller.device_config_invalid
        controller.start_voice()
        assert controller.voice_worker is None and not controller.voice_mic_open
        shell.full.audio_settings.reset_selection()
        assert not controller.device_config_invalid
        choice = {'name': 'USB mic', 'hostapi': 'Core Audio'}
        controller.set_devices(choice, None)
        assert json.loads(settings.value('audio/input_device')) == choice
        assert controller.input_choice == choice
        controller.voice_worker = object()
        controller.set_devices(None, None)
        assert controller.input_choice == choice  # A live session cannot be rerouted.
    finally:
        controller.voice_worker = None
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()

