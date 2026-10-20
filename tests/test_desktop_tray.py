"""Exercise the real menu without native tray, microphone or network."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QWidget
from jarvis.desktop.app import Controller, DesktopShell
from jarvis.desktop.tray import TrayControls, presence


@pytest.fixture
def controls():
    app = QApplication.instance() or QApplication([])
    c = Controller()
    shell = SimpleNamespace(controller=c, full=QWidget(), **{
        key: Mock() for key in ('show_full', 'show_compact', 'show_orb',
                               'show_details', 'show_settings', 'show_usage',
                               'show_metrics', 'hide_windows', 'quit')})
    tray = Mock()
    menu = TrayControls(shell, tray)
    yield app, c, shell, tray, menu
    menu.menu.close()
    shell.full.close()
    shell.full.deleteLater()


def test_tray_drives_shared_worker_and_reconnect_without_duplicates(controls):
    _, c, _, _, menu = controls
    c.start_voice = Mock()
    menu.session.trigger()
    c.start_voice.assert_called_once_with()
    worker = SimpleNamespace(stop=Mock(), set_muted=Mock(), interrupt=Mock())
    c.voice_worker = worker
    c.voice_event({'type': 'state', 'state': 'listening', 'mic_open': True})
    assert menu.session.text() == 'Arrêter le vocal'
    menu.microphone.trigger()
    worker.set_muted.assert_called_once_with(True)
    c.voice_event({'type': 'state', 'state': 'speaking', 'mic_open': True})
    menu.interrupt.trigger()
    worker.interrupt.assert_called_once_with()
    menu.session.trigger()
    worker.stop.assert_called_once_with()
    assert not menu.session.isEnabled()
    c.voice_state = 'error'
    c.can_reconnect = True
    c.changed.emit()
    assert not menu.session.isEnabled()  # still cleaning up the old worker
    menu.toggle_session()
    assert c.start_voice.call_count == 1
    c.voice_worker = None
    c.changed.emit()
    assert menu.session.text() == 'Reconnecter'
    menu.session.trigger()
    assert c.start_voice.call_count == 2


def test_tray_reflects_capture_and_local_test_without_exposing_payloads(controls):
    _, c, _, tray, menu = controls
    c.voice_worker = object()
    c.voice_error = 'PRIVATE_ERROR'
    c.voice_event({'type': 'state', 'state': 'listening', 'mic_open': True, 'input_suppressed': True})
    assert menu.status.text() == 'Écoute suspendue'
    assert menu.microphone_status.text() == 'Capture micro ouverte'
    before = tray.setIcon.call_count
    c.tool_notice = 'PRIVATE_TOOL_RESULT'
    c.changed.emit()
    assert tray.setIcon.call_count == before
    c.voice_worker = None
    c.voice_event({'type': 'state', 'state': 'off', 'mic_open': False})
    c.audio_worker = SimpleNamespace(stop=Mock())
    c.audio_job_kind = 'microphone'
    c.handle_audio_event({'type': 'audio_test', 'state': 'microphone'})
    assert presence(c)[0] == 'Test micro local · micro ouvert'
    assert not menu.session.isEnabled()
    assert menu.stop_test.isVisible()
    menu.stop_test.trigger()
    c.audio_worker.stop.assert_called_once_with()
    assert 'PRIVATE' not in str(tray.setToolTip.call_args_list)
    c.local_mic_open = False
    c.audio_worker = None
    c.voice_state = 'off'
    c.changed.emit()
    assert menu.microphone_status.text() == 'Capture micro fermée'
    assert not menu.stop_test.isVisible()


def test_tray_demo_cannot_start_capture_and_navigation_remains_available(controls):
    _, c, shell, _, menu = controls
    c.demo = True
    c.start_voice = Mock()
    c.changed.emit()
    assert not menu.session.isEnabled()
    menu.toggle_session()
    c.start_voice.assert_not_called()
    next(a for a in menu.menu.actions() if a.text() == 'Réglages audio').trigger()
    shell.show_settings.assert_called_once_with()
    next(a for a in menu.menu.actions() if a.text() == 'Masquer les fenêtres').trigger()
    shell.hide_windows.assert_called_once_with()


def test_hidden_windows_keep_session_and_settings_open_without_new_worker(monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    app = QApplication.instance() or QApplication([])
    class FakeTray:
        isSystemTrayAvailable = staticmethod(lambda: True)
        def __init__(self, parent):
            self.setContextMenu = Mock()
            self.setToolTip = Mock()
            self.setIcon = Mock()
            self.show = Mock()
            self.hide = Mock()
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon', FakeTray)
    c = Controller(demo=True)
    c.reduced_motion = True
    shell = DesktopShell(app, c, QSettings(str(tmp_path/'tray.ini'), QSettings.Format.IniFormat))
    try:
        assert shell.tray_controls.menu.parent() is shell.full
        shell.tray.setContextMenu.assert_called_once_with(shell.tray_controls.menu)
        shell.show_compact()
        shell.has_tray = False
        shell.hide_windows()
        assert shell.compact.isVisible()  # no tray: cannot strand the assistant
        shell.has_tray = True
        c.voice_worker = object()
        shell.hide_windows()
        assert not any(w.isVisible() for w in (shell.full, shell.compact, shell.orb_window))
        assert c.voice_worker is not None
        shell.show_settings()
        assert shell.full.isVisible() and shell.full.pages.currentIndex() == 3
        assert c.voice_worker is not None
    finally:
        c.voice_worker = None
        for window in (shell.full, shell.compact, shell.orb_window):
            window.hide()
