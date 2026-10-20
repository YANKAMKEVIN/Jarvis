"""Approved artwork, preference isolation and native selector regression checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from jarvis.desktop.appearances import CATALOG, AppearancePreference
from jarvis.desktop.avatar_assets import pose_image
from jarvis.desktop.avatar_selector import AvatarSelector
from jarvis.desktop.app import Controller, DesktopShell, STYLE

@pytest.fixture
def app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    return app

@pytest.mark.parametrize('appearance', CATALOG, ids=lambda a: a.id)
def test_artwork_decodes_and_atlas_poses_are_distinct(appearance):
    frames = [pose_image(appearance.id, state) for state in ('listening', 'thinking', 'speaking', 'success')]
    assert all(not f.isNull() and f.hasAlphaChannel() for f in frames)
    if appearance.atlas:
        assert frames[0].size().toTuple() == (627, 627)
        assert len({f.cacheKey() for f in frames}) == 4
        assert all(frames[0] != f for f in frames[1:])
    else:
        assert frames[0].width() >= 1254


def test_preference_default_invalid_and_disk_roundtrip(tmp_path):
    path = str(tmp_path / 'preferences.ini')
    settings = QSettings(path, QSettings.Format.IniFormat)
    pref = AppearancePreference(settings)
    assert pref.load() == 'nova_bot'
    for invalid in ('missing', None, ['nova_bot']):
        settings.setValue('appearance/avatar', invalid)
        assert pref.load() == 'nova_bot'
    pref.save('kitsune')
    settings.sync()
    assert AppearancePreference(QSettings(path, QSettings.Format.IniFormat)).load() == 'kitsune'


def test_selector_keyboard_and_live_modes_preserve_session(app, tmp_path, monkeypatch):
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable', lambda: False)
    settings = QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat)
    c = Controller(demo=True)
    shell = DesktopShell(app, c, settings)
    worker = object()
    c.voice_worker = worker
    from jarvis.desktop.presentation import project_task
    c.voice_event({'type': 'missions', 'missions': [project_task({
        'id': str(i), 'objective': f'Mission {i}', 'status': 'running', 'steps': []
    }) for i in range(2)]})
    missions = c.missions
    try:
        shell.show_full()
        shell.show_appearances()
        dialog = shell.appearance_dialog
        assert dialog.grid.count() == 16
        dialog.grid.setCurrentRow(0)
        QTest.keyClick(dialog.grid, Qt.Key.Key_Right)
        QTest.keyClick(dialog.grid, Qt.Key.Key_Space)
        assert c.appearance == 'neo_guide'
        dialog.grid.setCurrentRow(2)
        QTest.keyClick(dialog.grid, Qt.Key.Key_Return)
        assert c.appearance == 'kitsune'
        dialog.grid.setCurrentRow(1)
        QTest.keyClick(dialog.grid, Qt.Key.Key_Space)
        assert c.voice_worker is worker and c.missions is missions
        assert len(c.missions) == 2
        assert len([p for p in shell.full.assistant.mission.panels if p.isVisible()]) == 2
        for panel in (shell.full.assistant, shell.compact.assistant, shell.orb_window):
            assert panel.orb.appearance == 'neo_guide'
        assert shell.appearance_preference.load() == 'neo_guide'
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        assert not dialog.isVisible()
        shell.set_appearance('invalid')
        assert c.appearance == 'nova_bot'
        c.reduced_motion = True
        c.changed.emit()
        assert not shell.full.assistant.orb.timer.isActive()
        c.reduced_motion = False
        c.changed.emit()
        assert shell.full.assistant.orb.timer.isActive()
        shell.show_compact()
        app.processEvents()
        panel = shell.compact.assistant
        assert not panel.orb.geometry().intersects(panel.appearance_button.geometry())
        shell.show_orb()
        assert not shell.full.assistant.orb.timer.isActive()
        assert shell.orb_window.orb.timer.isActive()
        c.voice_event({'type': 'activity', 'id': 'result', 'label': 'Test', 'status': 'verified'})
        assert shell.orb_window.orb.state == 'success'
        c.clear_avatar_feedback()
        c.voice_event({'type': 'state', 'state': 'error'})
        assert shell.orb_window.orb.state == 'error'
    finally:
        c.voice_worker = None
        if shell.appearance_dialog: shell.appearance_dialog.hide()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()
