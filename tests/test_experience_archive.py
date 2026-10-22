from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace as NS
from unittest.mock import Mock
from jarvis.desktop.result_history import ResultHistoryStore,ResultRecorder,archive_receipt,RETENTION
from jarvis.desktop.live_runtime import LiveRuntime


def test_opt_in_results_persist_with_paths_and_expire_without_conversation(tmp_path):
    path=tmp_path/'private/results.db';store=ResultHistoryStore(path)
    row=archive_receipt('move_file','one',{'ok':True,'path':str(tmp_path/'report.txt'),'message':'File moved'},{'label':'Déplacement'})
    store.record(row);store.record(row)
    rows=ResultHistoryStore(path).list()
    assert len(rows)==1 and rows[0]['paths']==[str(tmp_path/'report.txt')]
    assert path.stat().st_mode&0o777==0o600
    old=dict(row,id='old',at=time.time()-RETENTION-1);store.record(old)
    assert len(store.list())==1
    store.clear();assert store.list()==[]


def test_history_redacts_obvious_secrets_and_never_archives_conversation(tmp_path):
    row=archive_receipt('ask_about_document','one',{'ok':True,'message':'password: Swordfish123!'}, {'label':'Document'})
    assert 'Swordfish' not in row['body']
    runtime=LiveRuntime(lambda event:None);runtime.set_profile({'history':True})
    runtime._conversation(NS(item=NS(id='one',role='assistant',text_content='PRIVATE_CONVERSATION')))
    assert runtime.result_recorder is None


def test_background_writer_finishes_and_reports_storage_failure_without_payload(tmp_path):
    store=ResultHistoryStore(tmp_path/'results.db')
    recorder=ResultRecorder(store);row=archive_receipt('test','one',{'ok':True,'message':'done'},{'label':'Test'})
    assert recorder.submit(row);recorder.close();assert len(store.list())==1
    assert not recorder.thread.is_alive() and not recorder.submit(row)
    errors=[];broken=ResultRecorder(NS(record=Mock(side_effect=sqlite3.OperationalError('PRIVATE_DB_ERROR'))),lambda:errors.append('unavailable'))
    broken.submit(row);broken.close();assert errors==['unavailable']
