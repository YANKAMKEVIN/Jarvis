"""Reproduce qualification failures without hardware or network."""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from jarvis.desktop.live_runtime import LiveRuntime
from jarvis.planner import PlannerEngine, ModelTurn
from jarvis.planner.model_wait import complete_bounded, ModelWaitStopped


def test_late_inference_never_completes_or_holds_cancellation():
    async def scenario():
        for cancelled in (False, True):
            entered, release, cancel = threading.Event(), threading.Event(), threading.Event()
            class Model:
                def complete(self, *_):
                    entered.set()
                    release.wait(2)
                    return ModelTurn(text='late')
            task = asyncio.create_task(PlannerEngine(Model(), [], max_seconds=.08).run('test', cancel))
            try:
                while not entered.is_set():
                    await asyncio.sleep(.001)
                if cancelled:
                    cancel.set()
                outcome = await asyncio.wait_for(task, .5)
                assert outcome.status == ('cancelled' if cancelled else 'budget_exceeded')
                assert not release.is_set()
            finally:
                release.set()
                await asyncio.sleep(.02)
    asyncio.run(scenario())


def test_cancelled_calls_keep_physical_capacity_until_provider_returns():
    async def scenario():
        release = threading.Event()
        entered = []
        class Model:
            def complete(self, *_):
                entered.append(1)
                release.wait(2)
                return ModelTurn(text='late')
        try:
            calls = [asyncio.create_task(complete_bounded(Model(), [], [], threading.Event(), .06)) for _ in range(20)]
            results = await asyncio.gather(*calls, return_exceptions=True)
            assert all(isinstance(r, ModelWaitStopped) for r in results)
            assert len(entered) == 2
        finally:
            release.set()
            await asyncio.sleep(.02)
    asyncio.run(scenario())


def test_atomic_admission_and_closed_runtime():
    runtime = LiveRuntime(lambda _: None)
    for submit, queue, limit in (
        (lambda: runtime.request_action('test', {}), runtime.desktop_requests, 10),
        (lambda: runtime.run_routine('test'), runtime.routine_requests, 10),
        (lambda: runtime.announce('test'), runtime.announcements, 32),
        (lambda: runtime.cancel_task('test'), runtime.task_cancellations, 32),
    ):
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: submit(), range(1000)))
        assert sum(results) == limit
        assert queue.qsize() == limit
    runtime.stop()
    assert not runtime.request_action('test', {})
    assert not runtime.run_routine('test')
    assert not runtime.announce('test')
    assert not runtime.cancel_task('test')


def test_mission_result_backpressure_preserves_order_and_stops():
    async def scenario():
        runtime = LiveRuntime(lambda _: None)
        for i in range(10):
            assert await runtime._announce_task(str(i))
        waiting = asyncio.create_task(runtime._announce_task('eleventh'))
        await asyncio.sleep(.03)
        assert not waiting.done()
        assert runtime.task_announcements.popleft()[1] == '0'
        assert await asyncio.wait_for(waiting, .2)
        assert [row[1] for row in runtime.task_announcements] == [str(i) for i in range(1,10)] + ['eleventh']
        waiting = asyncio.create_task(runtime._announce_task('stopped'))
        runtime.stop()
        assert await asyncio.wait_for(waiting, .2) is False
    asyncio.run(scenario())


def test_cancellation_during_native_action_waits_for_its_observed_result():
    from livekit.agents import function_tool
    from jarvis.planner import ScriptedModel, ToolCall

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        effects = []
        cancel = threading.Event()

        @function_tool(name='open_app', description='Simulated native action.')
        async def action(app_name: str) -> dict:
            entered.set()
            await release.wait()
            effects.append(app_name)
            return {'ok': True, 'state_confirmed': True}

        model = ScriptedModel([ModelTurn(tool_calls=[ToolCall('one', 'open_app', {'app_name': 'Test'})])])
        task = asyncio.create_task(PlannerEngine(model, [action]).run('test', cancel))
        try:
            await asyncio.wait_for(entered.wait(), .5)
            cancel.set()
            await asyncio.sleep(.03)
            assert not task.done()  # Do not pretend a physical action has stopped.
        finally:
            release.set()
        outcome = await asyncio.wait_for(task, .5)
        assert outcome.status == 'cancelled'
        assert effects == ['Test']
        assert len(outcome.steps) == 1 and outcome.steps[0].ok
    asyncio.run(scenario())
