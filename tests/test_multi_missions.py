"""Concurrency/resource tests: real planner loops, no native tools/network."""
import asyncio
from types import SimpleNamespace
from livekit.agents import function_tool
from jarvis.live.registry import ToolRegistry
from jarvis.planner import ModelTurn, PlannerEngine, ScriptedModel, ToolCall
from jarvis.planner.engine import TaskOutcome
from jarvis.planner.resources import DesktopGate
from jarvis.planner.tasks import TaskManager


async def until(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(poll(), 3)


def test_two_research_missions_overlap_third_waits_and_each_has_its_own_result():
    async def scenario():
        started, release = [], asyncio.Event()
        @function_tool(name='web_answer', description='Fake research')
        async def research(question: str) -> dict:
            started.append(question)
            await release.wait()
            return {'ok': True, 'message': question}
        def factory():
            return PlannerEngine(ScriptedModel([
                lambda messages: ModelTurn(tool_calls=[ToolCall(id='c', name='web_answer', arguments={'question': messages[1]['content']})]),
                ModelTurn(text='Recherche terminée')]), [research])
        manager = TaskManager(factory)
        ids = [manager.start(goal, read_only=True)['task_id'] for goal in ('alpha', 'beta', 'gamma')]
        await until(lambda: len(started) == 2)
        assert set(started) == {'alpha', 'beta'}
        assert manager.status(ids[2])['state'] == 'queued'
        release.set()
        await manager.wait()
        assert started == ['alpha', 'beta', 'gamma']
        assert all(manager.status(identifier)['last_task']['status'] == 'completed' for identifier in ids)
        assert len(set(ids)) == 3 and not manager.desktop_gate.busy
    asyncio.run(scenario())


def test_desktop_lease_covers_whole_plan_and_direct_voice_cannot_interfere():
    async def scenario():
        gate, release = DesktopGate(), asyncio.Event()
        entered = []
        registry = ToolRegistry.__new__(ToolRegistry)
        registry.desktop_gate = gate
        @registry._desktop_access
        async def direct():
            entered.append('direct')
            return {'ok': True}
        class Engine:
            async def run(self, goal, cancel, on_step):
                entered.append(goal)
                assert gate.owned
                if goal == 'first':
                    # Calls from the mission that owns the lease remain reentrant.
                    assert (await direct())['ok']
                    await release.wait()
                return TaskOutcome('completed', 'done')
        manager = TaskManager(Engine, desktop_gate=gate)
        first = manager.start('first')['task_id']
        second = manager.start('second')['task_id']
        await until(lambda: 'first' in entered)
        assert manager.status(second)['state'] == 'queued'
        assert (await direct())['error_code'] == 'desktop_busy'
        assert entered == ['first', 'direct']
        assert manager.cancel()['error_code'] == 'ambiguous_task'
        assert manager.cancel('missing')['error_code'] == 'task_not_found'
        assert manager.cancel(second)['cancel_requested']
        await until(lambda: manager.status(second).get('last_task', {}).get('status') == 'cancelled')
        assert 'second' not in entered
        release.set()
        await manager.wait()
        assert manager.status(first)['last_task']['status'] == 'completed'
        assert not gate.busy
        assert (await direct())['ok']
    asyncio.run(scenario())


def test_research_mode_cannot_execute_desktop_tools_even_if_model_requests_them():
    async def scenario():
        called, schemas = [], []
        @function_tool(name='open_app', description='Forbidden desktop operation')
        async def desktop() -> dict:
            called.append(True)
            return {'ok': True}
        class Model:
            def complete(self, messages, tools):
                schemas.append(tools)
                if len(messages) == 2:
                    return ModelTurn(tool_calls=[ToolCall(id='c', name='open_app', arguments={})])
                return ModelTurn(text='Action indisponible')
        manager = TaskManager(lambda: PlannerEngine(Model(), [desktop]))
        identifier = manager.start('Do not touch the desktop', read_only=True)['task_id']
        await manager.wait()
        outcome = manager.status(identifier)['last_task']
        assert outcome['steps'][0]['error_code'] == 'tool_not_allowed'
        assert not called
        assert all(s['function']['name'] != 'open_app' for batch in schemas for s in batch)
    asyncio.run(scenario())


def test_queue_is_bounded_and_session_shutdown_cancels_all_without_starting_waiters():
    async def scenario():
        entered = []
        class Engine:
            async def run(self, goal, cancel, on_step):
                entered.append(goal)
                await until(cancel.is_set)
                return TaskOutcome('cancelled', 'stopped')
        manager = TaskManager(Engine)
        ids = [manager.start(str(i))['task_id'] for i in range(6)]
        assert manager.start('overflow')['error_code'] == 'task_queue_full'
        await until(lambda: entered == ['0'])
        registry = ToolRegistry.__new__(ToolRegistry)
        registry.tasks = manager
        registry._web_task = registry._briefing_task = None
        await registry.aclose()
        assert entered == ['0']
        assert all(manager.status(i)['last_task']['status'] == 'cancelled' for i in ids)
        assert not manager.desktop_gate.busy and not manager.running
        assert manager.start('after close')['error_code'] == 'session_stopping'
    asyncio.run(scenario())


def test_failed_mission_releases_desktop_for_next_mission():
    async def scenario():
        called = []
        class Engine:
            async def run(self, goal, cancel, on_step):
                called.append(goal)
                if goal == 'fail':
                    raise RuntimeError('PRIVATE_FAILURE')
                return TaskOutcome('completed', 'done')
        manager = TaskManager(Engine)
        first = manager.start('fail')['task_id']
        second = manager.start('next')['task_id']
        await manager.wait()
        assert called == ['fail', 'next']
        assert manager.status(first)['last_task']['status'] == 'failed'
        assert manager.status(second)['last_task']['status'] == 'completed'
        assert not manager.desktop_gate.busy
        assert 'PRIVATE' not in str(manager.presentations())
    asyncio.run(scenario())


def test_cancelling_a_waiter_does_not_leak_a_resource():
    from jarvis.planner.resources import acquire
    async def scenario():
        lock = asyncio.Lock()
        await lock.acquire()
        async def waiting():
            async with acquire(lock):
                pass
        task = asyncio.create_task(waiting())
        await asyncio.sleep(0)
        lock.release()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert not lock.locked()
    asyncio.run(scenario())


def test_waiting_desktop_mission_does_not_block_parallel_research_slot():
    async def scenario():
        entered, release = [], asyncio.Event()
        @function_tool(name='open_app', description='Fake desktop')
        async def desktop() -> dict:
            entered.append('desktop')
            await release.wait()
            return {'ok': True}
        @function_tool(name='web_answer', description='Fake research')
        async def research() -> dict:
            entered.append('research')
            return {'ok': True}
        def factory():
            return PlannerEngine(ScriptedModel([
                lambda messages: ModelTurn(tool_calls=[ToolCall(id='c', name='web_answer' if messages[1]['content'] == 'research' else 'open_app', arguments={})]),
                ModelTurn(text='done')]), [desktop, research])
        manager = TaskManager(factory)
        manager.start('desktop')
        await until(lambda: entered == ['desktop'])
        second = manager.start('queued desktop')['task_id']
        manager.start('research', read_only=True)
        await until(lambda: 'research' in entered)
        assert entered == ['desktop', 'research']
        assert manager.status(second)['state'] == 'queued'
        manager.cancel(second)
        release.set()
        await manager.wait()
    asyncio.run(scenario())
