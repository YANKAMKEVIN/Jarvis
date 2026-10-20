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
        assert panel.orb.width() == 320
        assert not panel.open_button.isVisible() and not panel.menu_button.isVisible()
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

@pytest.mark.parametrize('appearance', CATALOG, ids=lambda a: a.id)
def test_choreography_bounds_and_reduced_motion(appearance):
    from jarvis.desktop.avatar_motion import MotionFrame, sample_motion
    for state in ('off', 'listening', 'thinking', 'speaking', 'success', 'error'):
        for phase in (0, .4, 1.7, 7, 50):
            frame = sample_motion(appearance.id, phase, 1, state)
            assert abs(frame.x) <= .02 and abs(frame.y) <= .02
            assert abs(frame.rotation) <= 3.1
            assert .95 <= frame.sx <= 1.05 and .95 <= frame.sy <= 1.05
            assert sample_motion(appearance.id, phase, 1, state, False) == MotionFrame()
    assert sample_motion(appearance.id, .7, 0, 'listening') != sample_motion(appearance.id, .7, 1, 'listening')


@pytest.mark.parametrize('appearance', CATALOG, ids=lambda a: a.id)
def test_each_choreography_renders_and_reduced_motion_is_still(app, appearance):
    from jarvis.desktop.visuals import Orb
    orb = Orb(180)
    orb.set_appearance(appearance.id)
    orb.state = 'listening'
    orb.show()
    app.processEvents()
    orb.timer.stop()  # Deterministic phase samples, no wall-clock dependency.
    try:
        orb.transition = 1
        orb.phase = .3
        first = orb.grab().toImage()
        orb.phase = 2.1
        second = orb.grab().toImage()
        assert first != second
        orb.set_motion(False)
        first = orb.grab().toImage()
        orb.phase = 40
        orb.energy = 1
        assert first == orb.grab().toImage()
        orb.set_motion(True)
        assert orb.timer.isActive()
        orb.hide()
        assert not orb.timer.isActive()
    finally:
        orb.hide()
        orb.deleteLater()


def test_catalog_has_distinct_choreography_signatures():
    from jarvis.desktop.avatar_motion import PROFILES, sample_motion
    assert set(PROFILES) == {a.id for a in CATALOG}
    signatures = {tuple(sample_motion(a.id, t, .4, 'listening') for t in (.2, .7, 2)) for a in CATALOG}
    assert len(signatures) == 16

@pytest.mark.parametrize('appearance', CATALOG[6:], ids=lambda a: a.id)
def test_abstract_idle_is_alive_and_interactions_differ_without_audio(appearance):
    from jarvis.desktop.avatar_motion import sample_motion
    states = ('off', 'listening', 'thinking', 'speaking', 'success', 'error')
    signatures = {tuple(sample_motion(appearance.id, phase, 0, state)
                        for phase in (.3, 1.2, 2.1)) for state in states}
    assert len(signatures) == len(states)
    idle = [sample_motion(appearance.id, phase, 0, 'off') for phase in (.3, 1.2, 2.1)]
    assert len(set(idle)) == 3  # No microphone or live voice worker needed.


def test_abstract_state_transitions_interpolate_without_resetting_motion_clock():
    from jarvis.desktop.avatar_motion import interaction_weights, ease_interaction, blended_motion, sample_motion
    for appearance in CATALOG[6:]:
        for state in ('listening', 'thinking', 'speaking', 'success', 'error'):
            weights = interaction_weights('off')
            weights = ease_interaction(weights, state)
            assert sum(weights.values()) == pytest.approx(1)
            actual = blended_motion(appearance.id, .7, 0, weights)
            start = sample_motion(appearance.id, .7, 0, 'off')
            end = sample_motion(appearance.id, .7, 0, state)
            for field in ('x','y','rotation','sx','sy'):
                assert getattr(actual,field) == pytest.approx(getattr(start,field)*.88 + getattr(end,field)*.12)
            for _ in range(100):
                weights = ease_interaction(weights, state)
            assert weights[state] == pytest.approx(1, abs=1e-5)


@pytest.mark.parametrize('appearance', CATALOG[6:], ids=lambda a: a.id)
def test_abstract_widget_moves_at_idle_and_responds_to_silent_interactions(app, appearance):
    from jarvis.desktop.visuals import Orb
    from jarvis.desktop.avatar_motion import interaction_weights
    orb = Orb(180)
    orb.set_appearance(appearance.id)
    orb.show()
    app.processEvents()
    orb.timer.stop()
    try:
        orb.transition = 1
        orb.phase = .3
        idle = orb.grab().toImage()
        orb.phase = 2.1
        assert idle != orb.grab().toImage()
        # Compare identical clock/audio values: the state drives a distinct render.
        captures = []
        for state in ('off','listening','thinking','speaking','success','error'):
            orb.state = state
            orb.interaction = interaction_weights(state)
            orb.phase = .7
            orb.transition = 1
            captures.append(orb.grab().toImage())
        assert all(captures[i] != captures[j] for i in range(6) for j in range(i))
        orb.set_motion(False)
        still = orb.grab().toImage()
        orb.phase = 100
        assert still == orb.grab().toImage()
    finally:
        orb.hide()
        orb.deleteLater()
