"""Erasure is checked in actual database files, not only through list()."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace as NS

import pytest
from jarvis.context_store import ContextStore
from jarvis.desktop.result_history import ResultHistoryStore
from jarvis.live.registry import create_live_registry
from jarvis.schedule.reminders import ReminderStore
from jarvis.schedule.store import ScheduledMessageStore

SENTINEL='qaErasureSentinelFictionOnly83261'


@pytest.mark.parametrize('journal',['DELETE','WAL'])
def test_archive_clear_removes_payload_from_database_and_wal(tmp_path,journal):
    path=tmp_path/'results.db';store=ResultHistoryStore(path)
    store.record({'id':'qa','at':time.time(),'tool':'qa','title':'QA','body':SENTINEL,'paths':[],'ok':True})
    with closing(sqlite3.connect(path)) as conn:conn.execute('PRAGMA journal_mode='+journal)
    store.clear()
    assert store.list()==[]
    for candidate in tmp_path.glob('results.db*'):
        assert SENTINEL.encode() not in candidate.read_bytes()


def test_context_clear_removes_payload_from_database(tmp_path):
    store=ContextStore(tmp_path/'context.db');store.add(SENTINEL)
    assert store.clear()==1 and store.recent()==[]
    assert SENTINEL.encode() not in store.path.read_bytes()


@pytest.mark.parametrize('scope',['reminders','scheduled'])
def test_confirmed_pending_purge_deletes_every_row_and_its_content(tmp_path,scope):
    reminder=ReminderStore(tmp_path/'reminders.db');scheduled=ScheduledMessageStore(tmp_path/'scheduled.db')
    target=reminder if scope=='reminders' else scheduled
    # Real persisted rows, deliberately above the old default list limit (50).
    for i in range(65):
        if scope=='reminders':reminder.add(SENTINEL+str(i),10000)
        else:scheduled.add('QA','Fictitious recipient',SENTINEL+str(i),10000)
    registry=create_live_registry(reminder_store=reminder,schedule_store=scheduled,
        memory_capability=NS(log_action=lambda *args,**kwargs:None,clear_missions=lambda:0))
    tools={tool.info.name:tool for tool in registry.livekit_tools()}
    async def scenario():
        prepared=await tools['clear_personal_data'](scope)
        assert prepared['requires_confirmation']
        assert len(target.list('pending',limit=100))==65
        return await tools['confirm_action'](prepared['token'])
    result=asyncio.run(scenario())
    assert result['ok'] and result['total_cleared']==65
    assert target.list(None,limit=100)==[]
    assert SENTINEL.encode() not in target.path.read_bytes()


def test_busy_wal_reader_prevents_false_full_erasure_claim(tmp_path):
    store=ResultHistoryStore(tmp_path/'results.db')
    row={'id':'one','at':time.time(),'tool':'qa','title':'QA','body':SENTINEL,'paths':[],'ok':True}
    store.record(row)
    with closing(sqlite3.connect(store.path)) as owner:
        owner.execute('PRAGMA journal_mode=WAL')
        store.record(dict(row,id='two'))
        owner.execute('BEGIN')
        owner.execute('SELECT * FROM results').fetchall()
        with pytest.raises(sqlite3.OperationalError,match='Effacement incomplet'):
            store.clear()
        owner.rollback()
    store.clear()
    assert store.list()==[]
    for candidate in tmp_path.glob('results.db*'):
        assert SENTINEL.encode() not in candidate.read_bytes()


def test_checklist_clear_removes_stored_item_text(tmp_path):
    from jarvis.capabilities.checklists import ChecklistsCapability
    store=ChecklistsCapability(tmp_path/'checklists.db')
    row=store.manage('create',text='QA list')
    assert store.manage('add',list_id=row.data['list_id'],text=SENTINEL).ok
    assert store.clear()==1
    assert SENTINEL.encode() not in store.path.read_bytes()


def test_mission_history_clear_removes_goal_text(tmp_path):
    from jarvis.memory.store import MemoryStore
    store=MemoryStore(tmp_path/'memory.db')
    store.log_mission(SENTINEL,'completed',1)
    assert store.clear_missions()==1
    assert store.recent_missions()==[]
    assert SENTINEL.encode() not in store.path.read_bytes()


def test_refused_secure_delete_closes_connection_before_sensitive_writes():
    from jarvis.storage_privacy import private_deletes
    conn=sqlite3.connect(':memory:')
    conn.set_authorizer(lambda action,*args: sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_PRAGMA else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):private_deletes(conn)
    with pytest.raises(sqlite3.ProgrammingError,match='closed'):conn.execute('SELECT 1')


def test_checkpoint_refuses_to_claim_erasure_inside_uncommitted_transaction():
    from jarvis.storage_privacy import checkpoint_erasure
    with closing(sqlite3.connect(':memory:')) as conn:
        conn.execute('CREATE TABLE test(value TEXT)')
        conn.execute('INSERT INTO test VALUES (?)',(SENTINEL,))
        with pytest.raises(sqlite3.ProgrammingError):checkpoint_erasure(conn)
        assert conn.in_transaction
        conn.rollback()


def test_forget_removes_payload_and_search_index_without_losing_other_memories(tmp_path):
    from jarvis.memory.store import MemoryStore
    store=MemoryStore(tmp_path/'memory.db')
    for i in range(30):store.remember('fact',f'QA subject {i}',f'qaftserasurefictionpayload{i}')
    selected=store.list()[15]
    with closing(sqlite3.connect(store.path)) as owner:
        owner.execute('PRAGMA journal_mode=WAL')
        assert store.delete(selected.id).id==selected.id
        assert store.search(selected.content)==[]
        assert len(store.list())==29
        for candidate in tmp_path.glob('memory.db*'):
            assert selected.content.lower().encode() not in candidate.read_bytes().lower()
