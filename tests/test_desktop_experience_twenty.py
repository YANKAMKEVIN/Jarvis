import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import asyncio
from concurrent.futures import Future
from types import SimpleNamespace as NS
from unittest.mock import Mock,AsyncMock
import json
from datetime import datetime
import pytest
from PySide6.QtCore import QSettings,QUrl,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton
from jarvis.desktop.app import Controller,DesktopShell,STYLE
from jarvis.desktop.experience_storage import save_trigger,load_triggers
from jarvis.desktop.document_drop import dropped_files,DocumentDropDialog
from jarvis.desktop.memory_editor import MemoryEditor
from jarvis.memory.store import MemoryStore
from jarvis.context_store import ContextStore


@pytest.fixture
def experience(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);app.setStyleSheet(STYLE)
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable',lambda:False)
    monkeypatch.setenv('JARVIS_MACROS_PATH',str(tmp_path/'macros.db'))
    monkeypatch.setenv('JARVIS_MEMORY_PATH',str(tmp_path/'memory.db'))
    monkeypatch.setenv('JARVIS_CONTEXT_PATH',str(tmp_path/'context.db'))
    monkeypatch.setenv('JARVIS_RESULT_HISTORY_PATH',str(tmp_path/'results.db'))
    c=Controller(demo=True);c.reduced_motion=True
    shell=DesktopShell(app,c,QSettings(str(tmp_path/'preferences.ini'),QSettings.Format.IniFormat));shell.show_compact();shell.finish_transfer()
    yield app,c,shell,shell.experience
    c.voice_worker=None;c.dance.stop();shell.experience.close()
    shell.recovery.close();shell.hold_hotkey.close();shell.power.close();shell.finish_transfer()
    if shell.voice_dialog:shell.voice_dialog.close()
    for w in (shell.full,shell.compact,shell.orb_window):w.hide()


def live(c):
    c.demo=False;c.voice_state='listening';c.voice_worker=NS(request_action=Mock(return_value=True),set_profile=Mock())
    return c.voice_worker


def test_palette_filters_and_runs_local_commands_without_a_microphone(experience):
    app,c,s,e=experience
    dialog=e.palette();dialog.search.setText('Préférences et réponses')
    assert dialog.list.count()==1
    QTest.keyClick(dialog.search,Qt.Key.Key_Return)
    assert e.dialogs['experience'].isVisible()
    assert c.voice_worker is None and not c.voice_mic_open
    assert len(s.compact.findChildren(QPushButton,options=Qt.FindChildOption.FindDirectChildrenOnly))==2


def test_briefing_is_read_only_and_preferences_update_without_replacing_worker(experience):
    app,c,s,e=experience;worker=live(c)
    e.set_option('tone','warm');e.set_option('detail','short');e.briefing()
    tool,args=worker.request_action.call_args.args
    assert tool=='run_task' and args['read_only'] is True
    assert 'cinq points' in args['goal'] and 'n’envoie rien' in args['goal']
    assert c.voice_worker is worker and worker.set_profile.call_args.args[0]['tone']=='warm'


def test_quiet_replies_are_opt_in_bounded_and_clearable(experience):
    app,c,s,e=experience
    c.voice_event({'type':'assistant_text','text':'not opted in'});assert c.quiet_replies==[]
    e.set_option('quiet',True)
    for i in range(8):c.voice_event({'type':'assistant_text','text':str(i)+'x'*5000})
    assert len(c.quiet_replies)==5 and all(len(r)<=4000 for r in c.quiet_replies)
    e.clear_replies();assert c.quiet_replies==[]


def test_voice_settings_ack_is_atomic_and_late_cancel_does_not_change_preferences(experience):
    app,c,s,e=experience
    receipt=Future();e.configure({'receipt':receipt,'appearance':'Neo Guide','voice':'not-a-voice'})
    assert not receipt.result()['ok'] and c.appearance=='nova_bot'
    receipt=Future();receipt.cancel();e.configure({'receipt':receipt,'appearance':'neo_guide'})
    assert c.appearance=='nova_bot'
    receipt=Future();e.configure({'receipt':receipt,'appearance':'Neo Guide','voice':'Kore','tone':'warm','detail':'short','quiet':True})
    assert receipt.result()['ok'] and c.appearance=='neo_guide' and e.options.quiet and c.selected_voice=='Kore'


def test_time_trigger_waits_for_session_and_never_opens_microphone(experience):
    app,c,s,e=experience
    save_trigger(s.settings,'Brief','time','09:00');e.reload_triggers()
    e.check_triggers(datetime(2026,10,22,9,0),set())
    assert len(e.pending)==1 and c.voice_worker is None
    e.check_triggers(datetime(2026,10,22,9,0),set());assert len(e.pending)==1
    worker=live(c);e.pump()
    worker.request_action.assert_called_once_with('run_macro',{'name':'Brief'})
    assert not e.pending and not c.voice_mic_open


def test_disabled_and_expired_triggers_never_dispatch(experience,monkeypatch):
    app,c,s,e=experience
    row=save_trigger(s.settings,'Brief','time','09:00');e.reload_triggers();e.check_triggers(datetime(2026,10,22,9,0),set())
    rows=load_triggers(s.settings);rows[0]['enabled']=False;s.settings.setValue('experience/triggers',json.dumps(rows));e.reload_triggers()
    assert not e.pending
    e.pending.append((-1000, row));worker=live(c);e.pump();worker.request_action.assert_not_called()


def test_app_launch_baseline_and_native_notification_are_debounced(experience):
    app,c,s,e=experience
    save_trigger(s.settings,'Review','application','Safari');e.reload_triggers()
    e.check_triggers(datetime(2026,10,22,10,0),{'safari'});assert not e.pending
    e.application_launched({'safari'});assert len(e.pending)==1
    e.application_launched({'safari'});assert len(e.pending)==1


def test_memory_editor_changes_only_selected_rows_and_context(experience,tmp_path):
    app,c,s,e=experience
    memory=MemoryStore(tmp_path/'test-memory.db');context=ContextStore(tmp_path/'test-context.db')
    memory.remember('preference','Ton','Court','user');memory.remember('preference','Langue','Français','user')
    dialog=MemoryEditor(memory=memory,context=context);e.show_dialog('memory',dialog)
    for i in range(dialog.list.count()):
        if dialog.list.item(i).data(Qt.ItemDataRole.UserRole)['subject']=='Ton':dialog.list.setCurrentRow(i);break
    dialog.content.setPlainText('Détaillé');dialog.save()
    assert memory.find_by_subject('preference','Ton').content=='Détaillé'
    assert memory.find_by_subject('preference','Langue').content=='Français'
    dialog.kind.setCurrentIndex(1);dialog.content.setPlainText('Préparer la réunion');dialog.save()
    identifier=context.recent()[0]['id'];dialog.list.setCurrentRow(0);dialog.content.setPlainText('Réunion terminée');dialog.save()
    assert context.recent()[0]['id']==identifier and context.recent()[0]['text']=='Réunion terminée'
    dialog.list.setCurrentRow(0);dialog.delete();assert context.recent()==[]


def test_drop_selects_without_reading_and_dispatches_chosen_guarded_tool(experience,tmp_path):
    app,c,s,e=experience
    path=tmp_path/'example.txt';path.write_text('private contents')
    urls=[QUrl.fromLocalFile(str(path))]
    e.drop(urls);dialog=e.dialogs['document']
    assert dialog.paths==[str(path)] and c.voice_worker is None
    assert not dialog.buttons[0].isEnabled()
    worker=live(c);c.changed.emit();dialog.buttons[0].click()
    tool,args=worker.request_action.call_args.args
    assert tool=='ask_about_document' and args['path']==str(path)
    assert 'private contents' not in str(args)
    with pytest.raises(ValueError):dropped_files([QUrl('https://example.com/file.txt')])


def test_theme_size_and_accessibility_do_not_change_avatar_or_session(experience):
    app,c,s,e=experience;worker=live(c);avatar=c.appearance
    e.set_option('theme','contrast');e.set_option('font_size',17);dialog=e.open()
    assert '#ffffff' in app.styleSheet() and '#000000' in app.styleSheet()
    assert 'font-size: 17px' in app.styleSheet()
    assert c.voice_worker is worker and c.appearance==avatar
    assert all(b.accessibleName() for b in dialog.findChildren(QPushButton))
    e.set_option('theme','night');e.set_option('font_size',13)
    assert '#82caff' in app.styleSheet()


def test_rig_cursor_and_reduced_motion_are_shared_without_opening_voice(experience):
    from jarvis.desktop.articulated_avatar import RIG_IDS
    app,c,s,e=experience;e.set_option('articulated',True);e.set_option('tracking',True)
    for appearance in RIG_IDS:
        s.set_appearance(appearance);image=s.compact.orb.grab().toImage()
        assert not image.isNull()
    assert s.compact.orb.articulated and s.full.assistant.orb.articulated
    assert not s.compact.orb.timer.isActive()  # Reduced motion remains authoritative.
    assert c.voice_worker is None


def test_archive_history_search_and_clear_leave_other_memories_untouched(experience,tmp_path):
    from jarvis.desktop.result_history import ResultHistoryStore,archive_receipt
    app,c,s,e=experience;file=tmp_path/'report.txt';file.write_text('report')
    archive=ResultHistoryStore();archive.record(archive_receipt('ask_about_document','receipt',{'ok':True,'message':'Résumé du rapport','path':str(file)},{'label':'Analyse du rapport'}))
    memory=MemoryStore();memory.remember('preference','Langue','Français','user')
    dialog=e.history();dialog.filter.setCurrentIndex(dialog.filter.findData('receipts'));dialog.search.setText('rapport')
    assert dialog.list.count()==1
    dialog.list.setCurrentRow(0);assert 'Résumé du rapport' in dialog.details.toPlainText() and str(file) in dialog.details.toPlainText()
    dialog.clear_archive();assert archive.list()==[]
    assert memory.find_by_subject('preference','Langue').content=='Français'


def test_articulated_dance_moves_limbs_and_reduced_motion_freezes_pixels(experience):
    from jarvis.desktop.visuals import Orb
    app,c,s,e=experience;orb=Orb(240);orb.articulated=True;orb.tracking=False;orb.show();orb.timer.stop()
    try:
        orb.dance=NS(active=True,elapsed=.1);one=orb.grab().toImage();before=bytes(one.constBits())
        orb.dance.elapsed=.3;two=orb.grab().toImage();assert before!=bytes(two.constBits())
        orb.set_motion(False);orb.phase=1;one=orb.grab().toImage();before=bytes(one.constBits())
        orb.phase=100;orb.dance.elapsed=5;two=orb.grab().toImage();assert before==bytes(two.constBits())
    finally:orb.hide();orb.deleteLater()


def test_voice_setting_receipt_crosses_real_qt_worker_boundary(experience,monkeypatch):
    from PySide6.QtCore import QThread,Signal
    from jarvis.desktop.presentation_tools import presentation_tools
    import time
    app,c,s,e=experience;threads=[];original=e.configure
    def configure(event):threads.append(QThread.currentThread()==app.thread());original(event)
    monkeypatch.setattr(e,'configure',configure)
    class Worker(QThread):
        event=Signal(object)
        def run(self):
            tool=presentation_tools(NS(presentation_observer=self.event.emit))[0]
            self.result=asyncio.run(tool(voice='Kore',tone='warm'))
    worker=Worker();worker.event.connect(c.voice_event);worker.start()
    deadline=time.monotonic()+5
    while worker.isRunning() and time.monotonic()<deadline:QTest.qWait(20)
    assert worker.wait(1000) and worker.result['ok']
    assert threads==[True] and c.selected_voice=='Kore' and e.options.tone=='warm'
