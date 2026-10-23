"""Scheduled outward actions: real persistence, fake recipients and sends only."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
import subprocess
import threading
from unittest.mock import patch

import pytest
from jarvis.capabilities.results import ToolResult
from jarvis.schedule.runner import deliver_due, macos_screen_unlocked
from jarvis.schedule.store import ScheduledMessageStore, ScheduleError


class Messaging:
    def __init__(self, confirmed=True, raises=False):
        self.calls=[];self.confirmed=confirmed;self.raises=raises
    def ensure_recipient(self, *args):
        return ToolResult.success('verify','verified')
    def send_text(self, app, text):
        self.calls.append((app,text))
        if self.raises:raise OSError('uncertain provider outcome')
        return ToolResult.success('send','accepted',command_executed=True,state_confirmed=self.confirmed)


def prepared(tmp_path, recurrence='none'):
    store=ScheduledMessageStore(tmp_path/'s.db')
    row=store.add('TestApp','QA recipient','QA text',100,recurrence)
    return store,row


@pytest.mark.parametrize('confirmed', [False,None])
def test_unconfirmed_send_is_not_successful_or_retried(tmp_path,confirmed):
    store,row=prepared(tmp_path,'daily');messaging=Messaging(confirmed)
    result=deliver_due(store,messaging,screen_unlocked=lambda:True,now=200)
    assert result['sent']==[]
    assert store.get(row['id'])['status']=='failed'
    assert store.list('pending')==[]
    deliver_due(ScheduledMessageStore(store.path),messaging,screen_unlocked=lambda:True,now=201)
    assert len(messaging.calls)==1


def test_exception_after_send_started_is_quarantined_without_retry(tmp_path):
    store,row=prepared(tmp_path);messaging=Messaging(raises=True)
    result=deliver_due(store,messaging,screen_unlocked=lambda:True,now=200)
    assert result['failed']
    assert store.get(row['id'])['status']=='failed'
    deliver_due(ScheduledMessageStore(store.path),messaging,screen_unlocked=lambda:True,now=201)
    assert len(messaging.calls)==1


def test_two_passes_do_not_send_the_same_message_twice(tmp_path):
    store,row=prepared(tmp_path,'daily');messaging=Messaging()
    due=store.due;barrier=threading.Barrier(2)
    def simultaneous(now):
        rows=due(now);barrier.wait(timeout=3);return rows
    with patch.object(store,'due',simultaneous),ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:deliver_due(store,messaging,screen_unlocked=lambda:True,now=200),range(2)))
    assert sum(len(r['sent']) for r in results)==1
    assert len(messaging.calls)==1
    assert len(store.list('pending'))==1


@pytest.mark.parametrize('front,info',[(NS(returncode=1,stdout=''),None),(NS(returncode=0,stdout=''),None),
    (NS(returncode=0,stdout='ASN:123'),NS(returncode=1,stdout='')),
    (NS(returncode=0,stdout='ASN:123'),NS(returncode=0,stdout='')),
    (NS(returncode=0,stdout='ASN:123'),NS(returncode=0,stdout='garbage')),
    (NS(returncode=0,stdout='ASN:123'),NS(returncode=0,stdout='"LSDisplayName"="loginwindow"'))])
def test_unknown_or_locked_screen_never_counts_as_unlocked(front,info):
    with patch('jarvis.schedule.runner.subprocess.run',side_effect=[front,info]):
        assert macos_screen_unlocked() is False


@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),float('-inf'),10**400])
def test_invalid_schedule_times_do_not_create_a_send(tmp_path,value):
    store=ScheduledMessageStore(tmp_path/'s.db')
    with pytest.raises(ScheduleError):store.add('TestApp','QA','text',value)
    assert store.list()==[]


def test_cancel_between_selection_and_claim_prevents_send(tmp_path):
    store,row=prepared(tmp_path);due=store.due;messaging=Messaging()
    def cancel_after_selection(now):
        rows=due(now);store.cancel(row['id']);return rows
    with patch.object(store,'due',cancel_after_selection):
        result=deliver_due(store,messaging,screen_unlocked=lambda:True,now=200)
    assert not result['sent'] and messaging.calls==[]
    assert store.get(row['id'])['status']=='cancelled'


def test_crash_left_claim_is_not_automatically_resent(tmp_path):
    store,row=prepared(tmp_path);messaging=Messaging()
    assert store.claim_delivery(row['id'])
    reopened=ScheduledMessageStore(store.path)
    assert reopened.get(row['id'])['status']=='sending'
    assert not reopened.cancel(row['id'])
    assert deliver_due(reopened,messaging,screen_unlocked=lambda:True,now=201)['sent']==[]
    assert messaging.calls==[]


def test_recurring_settlement_failure_cannot_trigger_another_send(tmp_path):
    import sqlite3
    from contextlib import closing
    store,row=prepared(tmp_path,'daily');messaging=Messaging()
    with closing(sqlite3.connect(store.path)) as conn,conn:
        conn.execute("CREATE TRIGGER reject_next BEFORE INSERT ON scheduled BEGIN SELECT RAISE(ABORT,'simulated storage failure'); END")
    with pytest.raises(sqlite3.Error):
        deliver_due(store,messaging,screen_unlocked=lambda:True,now=200)
    assert store.get(row['id'])['status']=='sending'
    assert len(store.list())==1
    deliver_due(ScheduledMessageStore(store.path),messaging,screen_unlocked=lambda:True,now=201)
    assert len(messaging.calls)==1


@pytest.mark.parametrize('name',['TestApp','Application avec espaces'])
def test_valid_native_screen_observation_is_accepted(name):
    with patch('jarvis.schedule.runner.subprocess.run',side_effect=[NS(returncode=0,stdout='ASN:123'),NS(returncode=0,stdout=f'"LSDisplayName"="{name}"\n')]):
        assert macos_screen_unlocked() is True


def test_different_recipients_are_serialized_across_workers(tmp_path):
    import time
    store,row=prepared(tmp_path)
    store.add('TestApp','QA second','second text',100)
    current=[None];observed=[]
    class SharedDesktop:
        def ensure_recipient(self,app,recipient):
            current[0]=recipient;time.sleep(.02)
            return ToolResult.success('verify','verified')
        def send_text(self,app,text):
            observed.append((current[0],text))
            return ToolResult.success('send','confirmed',state_confirmed=True,command_executed=True)
    messaging=SharedDesktop();due=store.due;barrier=threading.Barrier(2)
    def simultaneous(now):
        rows=due(now);barrier.wait(timeout=3);return rows
    with patch.object(store,'due',simultaneous),ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:deliver_due(store,messaging,screen_unlocked=lambda:True,now=200),range(2)))
    assert sorted(observed)==[('QA recipient','QA text'),('QA second','second text')]
    assert sum(len(r['sent']) for r in results)==2


def test_locking_screen_during_navigation_prevents_send(tmp_path):
    store,row=prepared(tmp_path);messaging=Messaging();states=iter([True,False])
    result=deliver_due(store,messaging,screen_unlocked=lambda:next(states),now=200)
    assert result['deferred'] and messaging.calls==[]
    assert store.get(row['id'])['status']=='pending'


@pytest.mark.parametrize("outcome", ["interrupted", "uncertain"])
def test_cli_exposes_interrupted_claim_for_manual_reconciliation(tmp_path,capsys,outcome):
    from jarvis.schedule.__main__ import cmd_list
    store,row=prepared(tmp_path)
    if outcome == "interrupted":store.claim_delivery(row['id'])
    else:deliver_due(store,Messaging(False),screen_unlocked=lambda:True,now=200)
    with patch('jarvis.schedule.__main__.ScheduledMessageStore',return_value=store):
        assert cmd_list()==0
    text=capsys.readouterr().out
    assert 'A verifier' in text and 'aucune relance automatique' in text


def test_voice_listing_exposes_uncertain_sends_without_requeueing(tmp_path):
    import asyncio
    from jarvis.live.registry import create_live_registry
    store,row=prepared(tmp_path)
    deliver_due(store,Messaging(False),screen_unlocked=lambda:True,now=200)
    registry=create_live_registry(schedule_store=store,memory_capability=NS(log_action=lambda *a,**k:None))
    tool=next(t for t in registry.livekit_tools() if t.info.name=='list_scheduled_messages')
    result=asyncio.run(tool())
    assert result['count']==0 and result['review_count']==1
    assert result['requires_review'][0]['id']==row['id']
    assert 'aucune relance automatique' in result['message']
    assert store.list('pending')==[]


def test_notification_failure_does_not_repeat_a_confirmed_send(tmp_path):
    store,row=prepared(tmp_path);messaging=Messaging()
    def broken_notice(_):raise OSError('notification unavailable')
    result=deliver_due(store,messaging,screen_unlocked=lambda:True,now=200,notifier=broken_notice)
    assert result['sent']==[row['id']]
    deliver_due(ScheduledMessageStore(store.path),messaging,screen_unlocked=lambda:True,now=201)
    assert len(messaging.calls)==1


def test_native_screen_probe_exception_refuses_delivery():
    with patch('jarvis.schedule.runner.subprocess.run',side_effect=FileNotFoundError):
        assert macos_screen_unlocked() is False


def test_verification_failure_never_sends_and_can_retry_safely(tmp_path):
    store,row=prepared(tmp_path);messaging=Messaging()
    messaging.ensure_recipient=lambda *args:(_ for _ in ()).throw(OSError('access unavailable'))
    result=deliver_due(store,messaging,screen_unlocked=lambda:True,now=200)
    assert result['deferred'] and messaging.calls==[]
    assert store.get(row['id'])['status']=='pending'


def test_malformed_send_result_is_quarantined_instead_of_crashing_or_retrying(tmp_path):
    store,row=prepared(tmp_path);messaging=Messaging()
    def broken_result(*args):
        messaging.calls.append(args)
        return NS(ok=True,data=None)
    messaging.send_text=broken_result
    result=deliver_due(store,messaging,screen_unlocked=lambda:True,now=200)
    assert result['failed'] and not result['sent']
    assert store.get(row['id'])['status']=='failed'
    deliver_due(ScheduledMessageStore(store.path),messaging,screen_unlocked=lambda:True,now=201)
    assert len(messaging.calls)==1


def test_independent_processes_preserve_recipient_and_send_once(tmp_path):
    import os
    import sys
    import time
    from pathlib import Path
    store,row=prepared(tmp_path)
    store.add('TestApp','QA second','second text',100)
    code='''
import os,sys,time
from pathlib import Path
from types import SimpleNamespace as NS
from jarvis.schedule.store import ScheduledMessageStore
from jarvis.schedule.runner import deliver_due
root=Path(sys.argv[1]);store=ScheduledMessageStore(root/'s.db');rows=store.due(200)
store.due=lambda _:rows
(root/('ready-'+sys.argv[2])).touch()
deadline=time.monotonic()+5
while not (root/'go').exists():
    if time.monotonic()>deadline:raise TimeoutError('test barrier')
    time.sleep(.005)
class Desktop:
    def ensure_recipient(self,app,recipient):
        (root/'target').write_text(recipient)
        time.sleep(.02)
        return NS(ok=True)
    def send_text(self,app,text):
        fd=os.open(root/'effects',os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
        try:os.write(fd,((root/'target').read_text()+'|'+text+'\\n').encode())
        finally:os.close(fd)
        return NS(ok=True,data={'state_confirmed':True})
deliver_due(store,Desktop(),screen_unlocked=lambda:True,now=200)
'''
    workers=[subprocess.Popen([sys.executable,'-c',code,str(tmp_path),str(i)],
        env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'src')},
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for i in range(2)]
    try:
        deadline=time.monotonic()+5
        while len(list(tmp_path.glob('ready-*')))<2:
            assert time.monotonic()<deadline
            time.sleep(.005)
        (tmp_path/'go').touch()
        for worker in workers:
            out,err=worker.communicate(timeout=5)
            assert worker.returncode==0,err
        assert sorted((tmp_path/'effects').read_text().splitlines())==['QA recipient|QA text','QA second|second text']
        assert len(store.list('sent'))==2
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill();worker.communicate(timeout=5)
