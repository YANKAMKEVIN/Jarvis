"""Compact companion stays avatar-first and preserves the shared voice/session."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from unittest.mock import Mock
from jarvis.desktop.app import Controller, DesktopShell, STYLE


@pytest.fixture
def companion(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable', lambda: False)
    c = Controller(demo=True)
    c.reduced_motion = True
    settings = QSettings(str(tmp_path/'companion.ini'), QSettings.Format.IniFormat)
    shell = DesktopShell(app,c,settings)
    shell.show_compact()
    app.processEvents()
    yield app,c,shell
    c.voice_worker = None
    if shell.appearance_dialog: shell.appearance_dialog.hide()
    shell.finish_transfer()
    for window in (shell.full,shell.compact,shell.orb_window):
        window.hide()
        window.deleteLater()
    app.processEvents()


def test_avatar_dominates_transparent_companion_and_only_hover_reveals_two_controls(companion):
    app,c,shell = companion
    window = shell.compact
    assert window.orb.width() == 320
    assert window.orb.height()/window.height() > .9
    assert window.width() == window.orb.width()
    assert window.status.isHidden()
    assert not window.open_button.isVisible() and not window.menu_button.isVisible()
    assert len(window.findChildren(QPushButton,options=Qt.FindChildOption.FindDirectChildrenOnly)) == 2
    before = window.orb.size()
    QApplication.sendEvent(window,QEnterEvent(QPointF(100,100),QPointF(100,100),QPointF(100,100)))
    assert window.open_button.isVisible() and window.menu_button.isVisible()
    assert window.orb.size() == before  # Hover does not resize or displace the avatar.
    QApplication.sendEvent(window,QEvent(QEvent.Type.Leave))
    assert not window.open_button.isVisible() and not window.menu_button.isVisible()
    image = window.grab().toImage()
    assert image.pixelColor(0,0).alpha() == 0
    assert image.pixelColor(image.width()-1,image.height()-1).alpha() == 0


def test_keyboard_reveals_controls_opens_full_window_and_escape_hides(companion):
    app,c,shell = companion
    window = shell.compact
    QTest.keyClick(window.orb, Qt.Key.Key_Space)
    assert window.open_button.isVisible() and window.menu_button.isVisible()
    QTest.keyClick(window.open_button,Qt.Key.Key_Tab)
    assert window.menu_button.hasFocus()
    QTest.keyClick(window.menu_button,Qt.Key.Key_Escape)
    assert not window.open_button.isVisible() and not window.menu_button.isVisible()
    QTest.keyClick(window.orb,Qt.Key.Key_Tab)
    assert window.open_button.isVisible()
    window.make_menu().actions_by_id['open_full'].trigger()
    assert shell.full.isVisible() and not window.isVisible()


def test_dragging_and_clicking_never_start_voice_or_open_full_window(companion):
    app,c,shell = companion
    c.demo = False
    c.start_voice = Mock()
    window = shell.compact
    origin = window.pos()
    QTest.mousePress(window.orb,Qt.MouseButton.LeftButton,pos=QPoint(90,90))
    QTest.mouseMove(window.orb,QPoint(140,110))
    QTest.mouseRelease(window.orb,Qt.MouseButton.LeftButton,pos=QPoint(140,110))
    assert window.pos() != origin
    assert shell.settings.value('companion/position') == window.pos()
    QTest.mouseClick(window.orb,Qt.MouseButton.LeftButton,pos=QPoint(100,100))
    assert window.isVisible() and not shell.full.isVisible()
    c.start_voice.assert_not_called()


def test_commands_preserve_session_and_two_missions_remain_accessible(companion):
    from jarvis.desktop.presentation import project_task
    app,c,shell = companion
    c.demo = False
    worker = Mock()
    c.voice_worker = worker
    c.voice_state = 'listening'
    c.voice_mic_open = True
    c.voice_event({'type':'missions','missions': [project_task({'id':str(i),
        'objective':f'Mission {i}','status':'running','steps':[]}) for i in range(2)]})
    missions = c.missions
    menu = shell.compact.make_menu()
    assert '2' in menu.actions_by_id['missions'].text()
    menu.actions_by_id['microphone'].trigger()
    worker.set_muted.assert_called_once_with(True)
    menu.actions_by_id['interrupt'].trigger()
    worker.interrupt.assert_called_once()
    shell.set_appearance('orbital_atlas')
    assert shell.compact.orb.appearance == 'orbital_atlas'
    assert c.voice_worker is worker and c.missions is missions
    menu.actions_by_id['missions'].trigger()
    assert shell.full.isVisible() and shell.full.pages.currentIndex() == 2
    shell.full.navigate(0)
    app.processEvents()
    assert len([panel for panel in shell.full.assistant.mission.panels if panel.isVisible()]) == 2
    shell.full.assistant.mission.panels[1].cancel.click()
    worker.cancel_task.assert_called_once_with('1')


def test_menu_stays_available_and_reflects_live_privacy_and_connection_states(companion):
    app,c,shell = companion
    window = shell.compact
    window.open_menu()
    app.processEvents()
    QApplication.sendEvent(window,QEvent(QEvent.Type.Leave))
    assert window.menu_open and window.menu_button.isVisible()
    c.voice_event({'type':'tool_receipt','label':'Rappel','status':'confirmation'})
    assert 'Accord vocal attendu' in window.menu.actions_by_id['notice'].text()
    assert 'Accord vocal attendu' in window.orb.toolTip()
    assert not window.menu.actions_by_id['session'].isEnabled()  # Demo cannot capture audio.
    window.menu.close()
    c.demo = False
    c.voice_worker = Mock()
    c.voice_state = 'error'
    c.changed.emit()
    menu = window.make_menu()
    assert not menu.actions_by_id['session'].isEnabled()
    assert not menu.actions_by_id['microphone'].isEnabled()
    c.voice_worker = None
    c.can_reconnect = True
    c.changed.emit()
    menu = window.make_menu()
    assert menu.actions_by_id['session'].text() == 'Reconnecter'
    assert menu.actions_by_id['session'].isEnabled()
    c.reduced_motion = False
    c.changed.emit()
    assert window.orb.timer.isActive()
    shell.show_full()
    assert not window.orb.timer.isActive()


def test_backchannel_menu_toggle_persists_and_reaches_every_avatar(companion):
    app,c,shell=companion
    window=shell.compact
    assert c.backchannel and window.orb.backchannel_enabled
    assert not window.make_menu().actions_by_id['backchannel'].isEnabled()  # Reduced motion: nothing to show.
    c.reduced_motion=False
    entry=window.make_menu().actions_by_id['backchannel']
    assert entry.isEnabled() and entry.isChecked()
    entry.trigger()
    app.processEvents()
    assert not c.backchannel and shell.settings.value('appearance/backchannel') in (False,'false')
    assert not window.orb.backchannel_enabled and not shell.orb_window.orb.backchannel_enabled
    assert not shell.full.assistant.orb.backchannel_enabled


def test_avatar_nods_silently_at_a_short_pause_while_listening(companion):
    app,c,shell=companion
    orb=shell.compact.orb
    orb.set_motion(True);orb.state='listening'
    nods=[]
    for level in [.08]*30+[.003]*27:
        orb.set_levels(level,0.0);orb.tick();nods.append(orb.listen.nod)
    assert orb.listen.attention>.5 and max(nods)>.9
    orb.grab()                                # paints the ring and the nod without error
    orb.backchannel_enabled=False;orb.tick()
    assert orb.listen.attention==0 and orb.listen.nod==0
