"""Qualification probes with simulated backends; no hardware, network or user data.

Exit 1 means a qualification criterion is unmet, even if unit CI is green.
The script does not change Jarvis. Blocking simulated providers are released in
finally blocks. Times describe a controlled scenario, not real-user performance.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from jarvis.planner import PlannerEngine,ModelTurn
from jarvis.planner.tasks import TaskManager
from jarvis.desktop.live_runtime import LiveRuntime

async def until(predicate):
    async def poll():
        while not predicate():await asyncio.sleep(.001)
    await asyncio.wait_for(poll(),2)

async def blocked_call(cancelled=False):
    entered=threading.Event();release=threading.Event();cancel=threading.Event()
    class Model:
        def complete(self,*args):entered.set();release.wait(2);return ModelTurn(text='Réponse de test tardive')
    engine=PlannerEngine(Model(),[],max_seconds=1 if cancelled else .03)
    task=asyncio.create_task(engine.run('Objectif de test',cancel))
    try:
        await until(entered.is_set)
        if cancelled:cancel.set()
        await asyncio.sleep(.08)
        pending=not task.done()
    finally:
        release.set();outcome=await asyncio.wait_for(task,2)
    if cancelled:
        return {'id':'QA-CANCEL','observation':{'pending_after_cancel':pending,'final_status':outcome.status},
                'criterion':'Cancellation of an in-flight model call returns promptly','passed':not pending and outcome.status=='cancelled'}
    return {'id':'QA-BUDGET','observation':{'pending_after_budget':pending,'final_status':outcome.status},
            'criterion':'A response received after the mission budget is not reported completed','passed':outcome.status=='budget_exceeded'}

async def queues():
    runtime=LiveRuntime(lambda event:None)
    for _ in range(10000):runtime.run_routine('routine');runtime.announce('Alerte de test')
    accepted=sum(runtime.request_action('run_task',{'goal':'test'}) for _ in range(10000))
    return {'id':'QA-QUEUES','observation':{'routines_queued':runtime.routine_requests.qsize(),'alerts_queued':runtime.announcements.qsize(),'desktop_requests_accepted':accepted},
            'criterion':'All producer paths apply admission control under a 10000-request burst',
            'passed':runtime.routine_requests.qsize()<10000 and runtime.announcements.qsize()<10000 and accepted<=10}

async def missions():
    release=threading.Event();lock=threading.Lock();active=peak=0
    class Model:
        def complete(self,*args):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            try:release.wait(2);return ModelTurn(text='Terminé')
            finally:
                with lock:active-=1
    manager=TaskManager(lambda:PlannerEngine(Model(),[]))
    outcomes=[manager.start(str(i),read_only=True) for i in range(100)]
    try:await until(lambda:peak==2)
    finally:release.set();await asyncio.wait_for(manager.wait(),3)
    accepted=sum(bool(row.get('ok')) for row in outcomes)
    return {'id':'QA-MISSIONS','observation':{'accepted':accepted,'rejected':len(outcomes)-accepted,'peak_concurrent_model_calls':peak},
            'criterion':'Mission requests are bounded to six live requests and two running plans','passed':accepted==6 and peak<=2}

async def probe():return [await blocked_call(),await blocked_call(True),await queues(),await missions()]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report={'backend':'Simulated; no measured real-service latency','checks':asyncio.run(probe())}
    report['qualified']=all(row['passed'] for row in report['checks'])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    for row in report['checks']:print(row['id'], 'PASS' if row['passed'] else 'NOT QUALIFIED',json.dumps(row['observation']))
    return 0 if report['qualified'] else 1
if __name__=='__main__':raise SystemExit(main())
