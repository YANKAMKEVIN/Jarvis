"""Dance must stay temporary, interruptible, and separate from voice/missions."""
import asyncio
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller, DesktopShell
from jarvis.desktop.avatar_dance import DANCERS, DURATION, dance_frame, travel
from jarvis.live.registry import create_live_registry


@pytest.fixture
def companion(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable', lambda: False)
    c = Controller(demo=True)
    shell = DesktopShell(app, c, QSettings(str(tmp_path/'dance.ini'), QSettings.Format.IniFormat))
    shell.show_compact()
    shell.finish_transfer()
    app.processEvents()
    yield app, c, shell
    c.dance.stop()
    shell.recovery.close(); shell.hold_hotkey.close(); shell.power.close()
    for widget in (shell.full, shell.compact, shell.orb_window):
        widget.hide()
    if shell.tray: shell.tray.hide()


def test_choreography_bounded_and_ends_neutral():
    for appearance in DANCERS:
        for index in range(801):
            t = index / 100
            frame = dance_frame(appearance, t)
            assert abs(frame.x) <= .035 and abs(frame.y) <= .025
            assert abs(frame.rotation) <= 9
            assert .975 <= frame.sx <= 1.025 and .975 <= frame.sy <= 1.025
            dx, dy = travel(t)
            assert abs(dx) <= 32 and -7 <= dy <= 0
        assert dance_frame(appearance, 0) == dance_frame(appearance, DURATION)
    assert travel(0) == travel(DURATION) == (0, 0)
    assert dance_frame('orbital_atlas', 1).rotation == 0


def test_voice_request_moves_returns_and_preserves_state(companion):
    app, c, shell = companion
    now = [100.]
    c.dance.clock = lambda: now[0]
    w = shell.compact
    area = w.screen().availableGeometry()
    origin = area.topLeft() + QPoint(60, 60)
    w.move(origin)
    c.missions['existing'] = {'id':'existing', 'status':'running', 'goal':'test'}
    c.voice_event({'type':'avatar_dance', 'action':'start'})
    now[0] += 1
    c.dance.tick()
    assert w.pos() != origin
    assert area.contains(w.geometry())
    assert c.voice_worker is None and c.voice_state == 'off'
    assert c.missions['existing']['status'] == 'running'
    c.demo = False
    shell.remember_companion()
    assert shell.settings.value('companion/position') == origin
    now[0] += 8
    c.dance.tick()
    assert not c.dance.active and not c.dance.timer.isActive()
    assert w.pos() == origin


def test_refusal_stopping_drag_and_appearance_change(companion):
    app, c, shell = companion
    c.reduced_motion = True
    assert not c.dance.start()
    c.reduced_motion = False
    c.appearance = 'orbital_atlas'
    assert not c.dance.start()
    c.appearance = 'nova_bot'
    assert c.dance.start()
    c.voice_event({'type':'avatar_dance', 'action':'stop'})
    assert not c.dance.active
    assert c.dance.start()
    QTest.mousePress(shell.compact.orb, Qt.MouseButton.LeftButton, pos=QPoint(100,100))
    assert not c.dance.active
    QTest.mouseRelease(shell.compact.orb, Qt.MouseButton.LeftButton, pos=QPoint(100,100))
    assert c.dance.start()
    shell.set_appearance('neo_guide')
    assert not c.dance.active
    assert c.dance.start()
    shell.compact.hide()
    assert not c.dance.active


def test_voice_tool_delivers_only_explicit_requests_and_excludes_planner():
    registry = create_live_registry()
    tools = {tool.info.name: tool for tool in registry.livekit_tools()}
    tool = tools['dance_avatar']
    assert asyncio.run(tool()) == {'ok':False, 'error':'desktop_unavailable'}
    events = []
    registry.set_presentation_observer(events.append)
    registry.read_only_mode = True
    assert asyncio.run(tool())['status'] == 'request_delivered'
    assert asyncio.run(tool(stop=True))['ok']
    assert events == [{'type':'avatar_dance','action':'start'}, {'type':'avatar_dance','action':'stop'}]
    assert 'dance_avatar' not in {tool.info.name for tool in registry.planner_tools}
    registry.set_presentation_observer(None)
    assert not asyncio.run(tool())['ok']


def test_edges_escape_and_duplicate_requests_keep_dance_bounded(companion):
    app, c, shell = companion
    now = [100.]
    c.dance.clock = lambda: now[0]
    w = shell.compact
    area = w.screen().availableGeometry()
    origin = QPoint(area.right()-w.width()+1, area.top())
    w.move(origin)
    c.dance.start()
    now[0] += 1
    c.dance.tick()
    assert area.contains(w.geometry())
    c.dance.start()
    assert c.dance.started == 100.  # Model retries never extend the eight seconds.
    QTest.keyClick(w.orb, Qt.Key.Key_Escape)
    assert not c.dance.active and w.pos() == origin
    c.dance.start()
    c.reduced_motion = True
    c.dance.tick()
    assert not c.dance.active and w.pos() == origin
    assert not w.make_menu().actions_by_id['dance'].isEnabled()
