import asyncio
from concurrent.futures import Future
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from jarvis.desktop.experience_core import ExperienceOptions,TurnProgress,UndoLedger,profile_instructions
from jarvis.desktop.experience_storage import due_triggers
from jarvis.desktop.setup_config import save_api_key


def test_corrupt_preferences_cannot_insert_arbitrary_instructions():
    class Settings:
        def value(self,key,default=None):return ['invalid']
    options=ExperienceOptions.load(Settings())
    assert options.tone=='balanced' and options.font_size==13
    assert 'invalid' not in profile_instructions(options.profile())


def test_progress_waits_without_replaying_or_interrupting_speech():
    now=[0.];progress=TurnProgress(lambda:now[0]);assert progress.received()['stage']=='received'
    now[0]=11;assert progress.poll('listening','speaking') is None
    assert progress.poll('listening','listening',True) is None
    assert progress.poll('listening','listening')['stage']=='waiting'
    assert progress.poll('listening','listening') is None
    progress.received();progress.response();assert progress.poll('listening','listening') is None


def moved_ticket(tmp_path):
    old=tmp_path/'old.txt';current=tmp_path/'current.txt';old.write_text('original');old.rename(current)
    ledger=UndoLedger();ledger.record('move_file',{'ok':True,'state_confirmed':True,'previous_path':str(old),'path':str(current)})
    return ledger,next(iter(ledger.tickets)),old,current


def test_undo_refuses_changed_files_and_occupied_origins(tmp_path):
    ledger,identifier,old,current=moved_ticket(tmp_path)
    assert ledger.validate(identifier)['new']==str(current)
    old.write_text('do not overwrite')
    with pytest.raises(ValueError,match='occupé'):ledger.validate(identifier)
    old.unlink();current.write_text('modified')
    with pytest.raises(ValueError,match='modifié'):ledger.validate(identifier)
    assert current.read_text()=='modified'


def test_undo_ignores_unverified_results_directories_and_symlinks(tmp_path):
    ledger=UndoLedger();folder=tmp_path/'folder';folder.mkdir();link=tmp_path/'link';link.symlink_to(folder,target_is_directory=True)
    for path in (folder,link):ledger.record('rename_file',{'ok':True,'state_confirmed':True,'previous_path':str(tmp_path/'old'),'path':str(path)})
    ledger.record('move_file',{'ok':True,'state_confirmed':False,'previous_path':'/old','path':'/new'})
    assert not ledger.tickets


def test_daily_trigger_runs_once_per_local_date_and_app_open_is_explicit():
    from datetime import datetime
    rows=[{'id':'daily','routine':'Brief','kind':'time','value':'09:00','enabled':True},
          {'id':'app','routine':'Review','kind':'application','value':'Safari','enabled':True}]
    now=datetime(2026,10,22,9,0)
    assert {r['id'] for r in due_triggers(rows,now,{'safari'})}=={'daily','app'}
    assert due_triggers(rows,now,set())==[]
    assert due_triggers(rows,datetime(2026,10,23,9,0),set())[0]['id']=='daily'
    rows[0]['enabled']=False;assert due_triggers(rows,datetime(2026,10,24,9,0),set())==[]


def test_key_write_is_private_atomic_and_preserves_other_configuration(tmp_path,monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY','test-before')
    root=tmp_path/'private';root.mkdir();(root/'desktop.env').write_text('JARVIS_GEMINI_LIVE_VOICE=Kore\nexport GOOGLE_API_KEY=old\n')
    path=save_api_key('A'*35,root)
    assert path.stat().st_mode&0o777==0o600 and root.stat().st_mode&0o777==0o700
    assert 'JARVIS_GEMINI_LIVE_VOICE=Kore' in path.read_text() and path.read_text().count('GOOGLE_API_KEY=')==1
    assert not list(root.glob('.desktop-*'))
    with pytest.raises(ValueError):save_api_key('bad\nvalue',root)
