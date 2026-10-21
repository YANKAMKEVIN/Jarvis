import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from jarvis.desktop.app import Controller,DesktopShell,STYLE
from jarvis.desktop.companion_preferences import CompanionPreferences
from jarvis.desktop.notifications import NoticeQueue
import pytest

@pytest.fixture
def ui(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);app.setStyleSheet(STYLE)
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable',lambda:False)
    c=Controller(demo=True);c.reduced_motion=True
    shell=DesktopShell(app,c,QSettings(str(tmp_path/'settings.ini'),QSettings.Format.IniFormat))
    shell.show_compact();app.processEvents()
    yield app,c,shell
    c.voice_worker=None
    shell.recovery.close();shell.hold_hotkey.close()
    for w in (shell.full,shell.compact,shell.orb_window): w.hide();w.deleteLater()
    app.processEvents()

def test_preferences_validate_and_persist(tmp_path):
    settings=QSettings(str(tmp_path/'prefs.ini'),QSettings.Format.IniFormat)
    settings.setValue('companion/size','broken');settings.setValue('companion/opacity',0)
    assert CompanionPreferences.load(settings)==CompanionPreferences()
    pref=CompanionPreferences(400,.65,'top_left',True,False);pref.save(settings);settings.sync()
    assert CompanionPreferences.load(QSettings(str(tmp_path/'prefs.ini'),QSettings.Format.IniFormat))==pref

def test_size_anchor_quiet_mode_and_live_session_are_independent(ui):
    app,c,shell=ui;w=shell.compact
    c.voice_worker=Mock();worker=c.voice_worker
    w.set_preference('size',400);w.set_preference('anchor','bottom_right');w.set_preference('opacity',.85)
    assert w.orb.width()==400 and w.width()==400 and c.voice_worker is worker
    assert w.screen().availableGeometry().contains(w.geometry())
    w.set_preference('quiet',True);w.enter_discreet();assert w.orb.width()==180
    w.reveal_controls();assert w.orb.width()==400
    c.voice_state='speaking';w.enter_discreet();assert not w.discreet
    w.hide();assert not w.idle_timer.isActive()

def test_contextual_voice_command_is_explicit_and_stateful(ui):
    app,c,shell=ui;c.demo=False;c.start_voice=Mock()
    shell.compact.render();shell.compact.voice_button.click();c.start_voice.assert_called_once()
    c.voice_worker=Mock();c.voice_state='listening';c.voice_mic_open=True;c.changed.emit()
    assert 'Couper' in shell.compact.voice_button.accessibleName()
    shell.compact.voice_button.click();c.voice_worker.set_muted.assert_called_once_with(True)
    c.voice_state='speaking';c.changed.emit();shell.compact.voice_button.click()
    c.voice_worker.interrupt.assert_called_once()
    c.voice_state='starting';c.changed.emit();assert not shell.compact.voice_button.isEnabled()

def test_notice_queue_deduplicates_bounds_and_drops_stale():
    now=[0];q=NoticeQueue(lambda:now[0])
    assert q.put('a','Done','mission');assert not q.put('a','Done','mission')
    now[0]=61;assert q.take() is None
    for i in range(10):q.put(str(i),'Done')
    assert len(q.pending)==5

def test_notifications_target_correct_mission_and_disable(ui):
    from jarvis.desktop.presentation import project_task
    app,c,shell=ui
    missions=[project_task({'id':str(i),'objective':'Test','status':'running','steps':[]}) for i in range(2)]
    c.voice_event({'type':'missions','missions':missions})
    c.voice_event({'type':'missions','missions':[dict(missions[0],status='completed'),missions[1]]})
    bubble=shell.compact.bubble
    assert bubble.current.mission_id=='0' and bubble.isVisible()
    c.voice_event({'type':'missions','missions':[dict(missions[0],status='completed'),missions[1]]})
    assert not bubble.queue.pending
    bubble.activate_notice()
    assert c.selected_mission_id=='0' and shell.full.pages.currentIndex()==2
    shell.show_compact();shell.compact.set_preference('bubbles',False)
    c.notice.emit({'key':'error','text':'Test'})
    assert not bubble.isVisible()

def test_hold_gate_never_captures_when_released_and_does_not_duplicate_worker(ui):
    app,c,shell=ui;c.demo=False;c.voice_worker=Mock();worker=c.voice_worker;c.voice_state='muted'
    c.set_push_to_talk(True)
    c.begin_push_to_talk();assert c.ptt_held and c.ptt_timer.isActive()
    worker.set_muted.assert_called_with(False)
    c.begin_push_to_talk();assert c.voice_worker is worker
    c.end_push_to_talk();worker.finish_push_to_talk.assert_called_once()
    assert not c.ptt_held and c.microphone_muted
    c.toggle_microphone();assert not c.ptt_held
    c.begin_push_to_talk();c.ptt_timer.timeout.emit()
    assert not c.ptt_held
    c.begin_push_to_talk();c.stop_voice()
    assert not c.ptt_held and not c.voice_desired

def test_ptt_release_during_connection_keeps_pending_worker_muted(ui):
    app,c,shell=ui;c.demo=False
    worker=Mock();c.ptt_enabled=True
    def start():c.voice_worker=worker;c.voice_state='starting'
    c.start_voice=start
    c.begin_push_to_talk();c.end_push_to_talk()
    worker.finish_push_to_talk.assert_called_once()
    assert c.microphone_muted and not c.ptt_held

def test_recovery_is_bounded_preserves_mute_and_never_overlaps_worker(ui):
    app,c,shell=ui
    r=shell.recovery;r.enabled=True;c.voice_desired=True;c.can_reconnect=True;c.voice_state='error';c.microphone_muted=True
    c.start_voice=Mock()
    for attempt,delay in enumerate((2000,5000,10000)):
        r.observe();assert r.timer.interval()==delay
        r.timer.stop();r.retry()
        assert r.attempts==attempt+1 and c.microphone_muted
    r.observe();assert not r.timer.isActive() and '3 essais' in c.recovery_message
    assert c.start_voice.call_count==3
    r.manual_start();c.voice_worker=Mock();r.retry()
    assert c.start_voice.call_count==3
    c.user_stop_requested=True;r.observe();assert not r.timer.isActive()

def test_sleep_wake_respects_stop_and_waits_for_old_worker(ui):
    app,c,shell=ui
    r=shell.recovery;r.enabled=True;c.voice_desired=True;c.voice_state='listening';c.voice_worker=Mock()
    worker=c.voice_worker;r.before_sleep()
    assert r.sleeping;worker.set_muted.assert_called_with(True);worker.stop.assert_called()
    r.after_wake();assert not r.timer.isActive()  # The old worker still owns its streams.
    c.voice_worker=None;c.voice_state='off';c.changed.emit()
    assert r.timer.isActive()
    r.timer.stop();c.stop_voice();r.after_wake()
    assert not r.timer.isActive() and not c.voice_desired

def test_routine_templates_are_configuration_not_execution(ui,tmp_path):
    from jarvis.desktop.routines import RoutineDialog
    from jarvis.macros import MacroStore
    app,c,shell=ui
    store=MacroStore(tmp_path/'macros.db');dialog=RoutineDialog(c,store=store)
    try:
        dialog.template('Ma journée');assert not store.list()
        dialog.save();assert store.get('Ma journée')
        assert not dialog.run.isEnabled()
        c.demo=False;c.voice_worker=Mock();c.voice_state='listening';c.changed.emit()
        dialog.launch();c.voice_worker.run_routine.assert_called_once_with('Ma journée')
        dialog.delete();assert not store.list()
    finally:dialog.close();dialog.deleteLater()
