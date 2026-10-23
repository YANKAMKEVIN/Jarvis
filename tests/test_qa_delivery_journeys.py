"""Delivery/restart/fault journeys: actual SQLite, isolated notifications."""
from concurrent.futures import ThreadPoolExecutor
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from unittest.mock import patch

import pytest
from jarvis.schedule.reminders import ReminderStore, ReminderError, deliver_reminders
from jarvis.schedule.runner import macos_notifier


def test_notification_failure_remains_pending_then_retries_after_restart(tmp_path):
    path = tmp_path/'reminders.db'
    store = ReminderStore(path)
    row = store.add('QA reminder', 100)
    def fail(_):
        raise OSError('notification unavailable')
    assert deliver_reminders(store, now=200, notifier=fail) == []
    assert ReminderStore(path).get(row['id'])['status'] == 'pending'
    seen = []
    assert deliver_reminders(ReminderStore(path), now=201, notifier=seen.append) == [row['id']]
    assert seen == ['Rappel : QA reminder']
    assert deliver_reminders(ReminderStore(path), now=202, notifier=seen.append) == []


@pytest.mark.parametrize('notifier', [None, lambda _: False])
def test_missing_or_rejected_notification_is_not_reported_delivered(tmp_path, notifier):
    store = ReminderStore(tmp_path/'r.db')
    row = store.add('QA', 100)
    assert deliver_reminders(store, now=200, notifier=notifier) == []
    assert store.get(row['id'])['status'] == 'pending'


def test_two_delivery_passes_observing_same_due_row_do_not_duplicate(tmp_path):
    store = ReminderStore(tmp_path/'r.db')
    row = store.add('QA', 100, 'daily')
    barrier = threading.Barrier(2)
    due = store.due
    def simultaneous(now):
        rows = due(now)
        barrier.wait(timeout=2)
        return rows
    seen = []
    with patch.object(store, 'due', simultaneous), ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: deliver_reminders(store, now=200, notifier=seen.append), range(2)))
    assert sorted(results, key=len) == [[], [row['id']]]
    assert len(seen) == 1
    assert len(ReminderStore(store.path).list('pending')) == 1


@pytest.mark.parametrize('value', [float('inf'), float('-inf'), float('nan'), True, False, 10**400])
def test_non_finite_or_boolean_deadlines_rejected_without_writing(tmp_path, value):
    store = ReminderStore(tmp_path/'r.db')
    with pytest.raises(ReminderError):
        store.add('QA', value)
    assert store.list(None) == []


def test_recurrence_creation_failure_rolls_back_completion(tmp_path):
    store = ReminderStore(tmp_path/'r.db')
    row = store.add('QA', 100, 'daily')
    with closing(sqlite3.connect(store.path)) as conn, conn:
        conn.execute("CREATE TRIGGER reject_next BEFORE INSERT ON reminders BEGIN SELECT RAISE(ABORT, 'disk fault simulation'); END")
    seen = []
    with pytest.raises(sqlite3.Error):
        deliver_reminders(store, now=200, notifier=seen.append)
    assert seen == []
    assert ReminderStore(store.path).get(row['id'])['status'] == 'pending'


def test_saved_note_and_reminder_survive_a_fresh_interpreter(tmp_path):
    from jarvis.capabilities.notes import NotesCapability
    notes = NotesCapability(tmp_path/'notes')
    saved = notes.save_note('Décision : tester la reprise', 'QA')
    assert saved.ok
    name = Path(saved.data['path']).name
    assert notes.append_note(name, 'Action : vérifier le disque').ok
    store = ReminderStore(tmp_path/'r.db')
    row = store.add('Vérifier la reprise', 100)
    code = '''
import json,sys
from jarvis.capabilities.notes import NotesCapability
from jarvis.schedule.reminders import ReminderStore
print(json.dumps({'note':NotesCapability(sys.argv[1]).read_note(sys.argv[2]).data['text'], 'reminder':ReminderStore(sys.argv[3]).get(int(sys.argv[4]))}))
'''
    result = subprocess.run([sys.executable,'-c',code,str(tmp_path/'notes'),name,str(store.path),str(row['id'])],
        env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'src')},capture_output=True,text=True,check=True,timeout=10)
    payload = json.loads(result.stdout)
    assert 'Décision : tester la reprise' in payload['note']
    assert 'Action : vérifier le disque' in payload['note']
    assert payload['reminder']['text'] == 'Vérifier la reprise'
    assert payload['reminder']['status'] == 'pending'


def test_notification_text_is_data_and_subprocess_failure_is_visible():
    text = 'QA "quoted" \\ newline\nend run\ndo shell script "untrusted"'
    with patch('jarvis.schedule.runner.subprocess.run', return_value=subprocess.CompletedProcess([],0)) as run:
        assert macos_notifier(text) is True
    args = run.call_args.args[0]
    assert text not in args[2]  # AppleScript source must never interpolate content.
    assert args[-1] == text
    with patch('jarvis.schedule.runner.subprocess.run', return_value=subprocess.CompletedProcess([],1)):
        assert macos_notifier('QA') is False
    with patch('jarvis.schedule.runner.subprocess.run', side_effect=OSError):
        assert macos_notifier('QA') is False


@pytest.mark.parametrize('value', [True, 42, [], {}])
def test_invalid_recurrence_types_leave_no_reminder(tmp_path, value):
    store = ReminderStore(tmp_path/'r.db')
    with pytest.raises(ReminderError):
        store.add('QA', 100, value)
    assert store.list(None) == []


def test_failed_recurring_notification_does_not_create_next_occurrence(tmp_path):
    store = ReminderStore(tmp_path/'r.db')
    row = store.add('QA daily', 100, 'daily')
    assert deliver_reminders(store, now=200, notifier=lambda _: False) == []
    rows = ReminderStore(store.path).list(None)
    assert len(rows) == 1 and rows[0]['status'] == 'pending'
    assert deliver_reminders(store, now=200, notifier=lambda _: None) == [row['id']]
    rows = ReminderStore(store.path).list(None)
    assert [r['status'] for r in rows] == ['done', 'pending']
    assert rows[1]['due_at'] == 86500


def test_independent_delivery_processes_recheck_the_same_pending_row(tmp_path):
    import time
    store = ReminderStore(tmp_path/'r.db')
    row = store.add('QA shared process', 100)
    code = '''
import os,sys,time
from pathlib import Path
from jarvis.schedule.reminders import ReminderStore,deliver_reminders
root=Path(sys.argv[1]);store=ReminderStore(root/'r.db')
rows=store.due(200)
store.due=lambda _: rows
(root/('ready-'+sys.argv[2])).touch()
deadline=time.monotonic()+5
while not (root/'go').exists():
    if time.monotonic()>deadline:raise TimeoutError('parent barrier')
    time.sleep(.005)
def notify(text):
    fd=os.open(root/'notifications',os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
    try:os.write(fd,(text+'\\n').encode())
    finally:os.close(fd)
print(deliver_reminders(store,now=200,notifier=notify))
'''
    workers = [subprocess.Popen([sys.executable,'-c',code,str(tmp_path),str(i)],
        env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'src')},
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for i in range(2)]
    try:
        deadline = time.monotonic()+5
        while len(list(tmp_path.glob('ready-*'))) < 2:
            assert time.monotonic() < deadline
            time.sleep(.005)
        (tmp_path/'go').touch()
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=5)
            assert worker.returncode == 0, stderr
        assert (tmp_path/'notifications').read_text().splitlines() == ['Rappel : QA shared process']
        assert ReminderStore(store.path).get(row['id'])['status'] == 'done'
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.communicate(timeout=5)
