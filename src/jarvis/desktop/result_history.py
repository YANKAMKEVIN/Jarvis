"""Opt-in local tool-result archive. No conversation, recording or remote sync."""
import json
import os
import sqlite3
from jarvis.storage_privacy import private_deletes, checkpoint_erasure
import time
from pathlib import Path
from contextlib import closing
from queue import Queue,Full,Empty
from threading import Thread,Event
from jarvis.memory.guard import contains_secret

RETENTION=30*24*3600


def archive_receipt(tool,identifier,result,projected):
    if not isinstance(result,dict):return None
    card=projected.get('card') or {}
    title=str(card.get('title') or projected.get('label') or 'Résultat d’outil')[:160]
    if contains_secret(title):title='Résultat d’outil'
    body='\n'.join([str(card.get('body','')),*(str(value) for value in card.get('items',[])[:30])]).strip()
    if not body:body=str(result.get('message',''))
    body=body[:10000]
    if contains_secret(body):body='Contenu sensible détecté : non conservé.'
    paths=[]
    for key in ('path','destination','created_path'):
        value=result.get(key)
        if isinstance(value,str) and len(value)<=2048 and Path(value).is_absolute() and value not in paths and not contains_secret(Path(value).name) and not contains_secret(str(Path(value).parent), high_entropy=False):paths.append(value)
    return {'id':identifier,'tool':tool,'title':title,'body':body,'paths':paths,'ok':bool(result.get('ok')),'at':time.time()}


class ResultHistoryStore:
    def __init__(self,path=None):
        self.path=Path(path or os.environ.get('JARVIS_RESULT_HISTORY_PATH') or Path.home()/'Library/Application Support/Jarvis/results.db')
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);os.chmod(self.path.parent,0o700)
        if not self.path.exists():self.path.touch(mode=0o600)
        os.chmod(self.path,0o600)
        conn=private_deletes(sqlite3.connect(self.path,timeout=1));conn.row_factory=sqlite3.Row
        conn.execute('CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, at REAL NOT NULL, tool TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, paths TEXT NOT NULL, ok INTEGER NOT NULL)')
        return conn
    def record(self,row):
        with closing(self.connect()) as conn,conn:
            conn.execute('INSERT OR IGNORE INTO results VALUES (?,?,?,?,?,?,?)',(row['id'],row['at'],row['tool'][:80],row['title'][:160],row['body'][:10000],json.dumps(row['paths'][:5]),int(row['ok'])))
            conn.execute('DELETE FROM results WHERE at < ?',(time.time()-RETENTION,))
            conn.execute('DELETE FROM results WHERE id NOT IN (SELECT id FROM results ORDER BY at DESC LIMIT 1000)')
    def list(self):
        with closing(self.connect()) as conn,conn:
            conn.execute('DELETE FROM results WHERE at < ?',(time.time()-RETENTION,))
            rows=conn.execute('SELECT * FROM results ORDER BY at DESC LIMIT 200').fetchall()
        return [dict(row,paths=json.loads(row['paths'])) for row in rows]
    def clear(self):
        with closing(self.connect()) as conn,conn:
            conn.execute('DELETE FROM results')
            conn.commit()
            checkpoint_erasure(conn)


class ResultRecorder:
    """A bounded background writer; database latency never blocks voice controls."""
    def __init__(self,store=None,on_error=None):
        self.on_error=on_error or (lambda:None);self.reported=False
        self.store=store or ResultHistoryStore();self.queue=Queue(maxsize=32);self.stopped=Event();self.thread=None
    def submit(self,row):
        if self.stopped.is_set():return False
        if self.thread is None:self.thread=Thread(target=self.run,name='jarvis-results',daemon=True);self.thread.start()
        try:self.queue.put_nowait(row);return True
        except Full:return False
    def run(self):
        while not self.stopped.is_set() or not self.queue.empty():
            try:row=self.queue.get(timeout=.1)
            except Empty:continue
            try:self.store.record(row);self.reported=False
            except (OSError,sqlite3.Error):
                if not self.reported:self.reported=True;self.on_error()
    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=1)
            if self.thread.is_alive():
                while True:
                    try:self.queue.get_nowait()
                    except Empty:break
                self.on_error()
                self.thread.join(timeout=1.2)
