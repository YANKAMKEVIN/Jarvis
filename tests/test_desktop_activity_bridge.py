"""Real registry decorator and planner progress, with no native tool construction."""
import asyncio
from jarvis.live.registry import ToolRegistry
from jarvis.planner.tasks import TaskManager
from jarvis.planner.engine import StepRecord, TaskOutcome


def test_observer_tracks_actual_tool_lifecycle_and_never_changes_its_result():
    async def scenario():
        registry = ToolRegistry.__new__(ToolRegistry)
        events = []
        registry.set_activity_observer(events.append)
        async def log(*args): pass
        registry._log_action = log
        @registry._journaled('open_app')
        async def success(): return {'ok': True}
        assert await success() == {'ok': True}
        assert [e['phase'] for e in events] == ['started', 'result']
        assert events[0]['id'] == events[1]['id']
        @registry._journaled('open_app')
        async def failure(): raise ValueError('PRIVATE_PROVIDER_ERROR')
        try:
            await failure()
        except ValueError:
            pass
        else:
            raise AssertionError('Tool errors must still propagate')
        assert events[-1]['phase'] == 'error'
        assert 'PRIVATE' not in str(events)
        registry.set_activity_observer(lambda event: (_ for _ in ()).throw(RuntimeError('observer failed')))
        assert await success() == {'ok': True}
    asyncio.run(scenario())


def test_planner_progress_reports_cooperative_cancellation_before_actual_end():
    async def scenario():
        release = asyncio.Event()
        class Engine:
            async def run(self, goal, cancel, on_step):
                step = StepRecord('open_app', True, False)
                on_step(step)
                await release.wait()
                return TaskOutcome('cancelled' if cancel.is_set() else 'completed', 'PRIVATE_SUMMARY', [step])
        manager = TaskManager(Engine)
        assert manager.progress() is None
        assert manager.start('PRIVATE_GOAL')['task_started']
        await asyncio.sleep(0)
        first = manager.progress()
        assert first['status'] == 'running' and first['step_count'] == 1
        manager.cancel()
        assert manager.progress()['status'] == 'cancelling'
        assert 'PRIVATE' not in str(manager.progress())
        release.set()
        await manager.wait()
        assert manager.progress()['status'] == 'cancelled'
        assert manager.progress()['id'] == first['id']
        manager.start('another task')
        assert manager.progress()['id'] != first['id']
        await manager.wait()
    asyncio.run(scenario())


def test_background_web_completion_reaches_cards_without_changing_voice_notification():
    from jarvis.capabilities.results import ToolResult
    from jarvis.desktop.live_runtime import LiveRuntime
    async def scenario():
        registry = ToolRegistry.__new__(ToolRegistry)
        class Knowledge:
            def answer(self, question):
                return ToolResult.success('web_answer', 'Réponse sourcée', external_knowledge_retrieved=True,
                    sources=[{'title': 'Source', 'url': 'https://example.com/read?id=1'}])
        registry.knowledge = Knowledge()
        events, spoken = [], []
        runtime = LiveRuntime(events.append)
        registry.set_activity_observer(runtime._registry_activity)
        async def log(*args): pass
        async def notify(message): spoken.append(message)
        registry._log_action = log
        registry.set_task_notifier(notify)
        await registry._run_web_search('PRIVATE_QUESTION')
        assert events[-1]['id'] == 'background:web'
        assert events[-1]['card']['body'] == 'Réponse sourcée'
        assert 'PRIVATE_QUESTION' not in str(events)
        assert spoken and 'Réponse sourcée' in spoken[0]
    asyncio.run(scenario())


def test_actual_vision_tools_emit_lifecycle_even_when_disabled_or_failing():
    from types import SimpleNamespace
    from jarvis.capabilities.results import ToolResult
    from jarvis.desktop.live_runtime import LiveRuntime
    async def scenario():
        registry = ToolRegistry.__new__(ToolRegistry)
        events, logs = [], []
        runtime = LiveRuntime(events.append)
        registry.set_activity_observer(runtime._registry_activity)
        async def log(*args): logs.append(args)
        registry._log_action = log
        registry.vision_lock = asyncio.Lock()
        registry._vision_guard = lambda name: {'ok': False, 'error_code': 'vision_disabled'}
        registry._debug_vision_result = lambda *args: None
        tools = {tool.info.name: tool for tool in registry.livekit_tools()}
        result = await tools['describe_screen']()
        assert not result['ok']
        assert [e['status'] for e in events] == ['running', 'error']
        assert all(e['screen'] for e in events)
        registry._vision_guard = lambda name: None
        def analyze(*args):
            return ToolResult.success('ask_about_screen', 'Une erreur est affichée',
                analysis='Une erreur est affichée', source='window', image_path='PRIVATE_PATH')
        registry.vision = SimpleNamespace(ask_about_screen=analyze)
        await tools['ask_about_screen']('PRIVATE_QUESTION')
        assert events[-1]['card']['body'] == 'Une erreur est affichée'
        assert events[-2]['id'] == events[-1]['id']
        def fail(*args): raise RuntimeError('PRIVATE_PROVIDER_ERROR')
        registry.vision.ask_about_screen = fail
        try:
            await tools['ask_about_screen']('PRIVATE_QUESTION')
        except RuntimeError:
            pass
        else:
            raise AssertionError('Provider exception should propagate')
        assert events[-1]['status'] == 'error'
        assert 'PRIVATE' not in str(events)
    asyncio.run(scenario())


def test_mission_presentation_tracks_inflight_tool_and_excludes_result_text():
    from livekit.agents import function_tool
    from jarvis.planner import ModelTurn, PlannerEngine, ScriptedModel, ToolCall
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        @function_tool(name='open_app', description='Fake application tool')
        async def open_app() -> dict:
            entered.set()
            await release.wait()
            return {'ok': True, 'state_confirmed': True, 'message': 'PRIVATE_RESULT'}
        manager = TaskManager(lambda: PlannerEngine(ScriptedModel([
            ModelTurn(tool_calls=[ToolCall(id='a', name='open_app', arguments={})]),
            ModelTurn(text='PRIVATE_SUMMARY')]), [open_app]))
        manager.start('Ouvrir une application')
        await asyncio.wait_for(entered.wait(), 3)
        snapshot = manager.presentation()
        assert snapshot['objective'] == 'Ouvrir une application'
        assert snapshot['current_tool'] == 'open_app' and snapshot['steps'] == []
        assert 'objective' not in manager.progress()
        release.set()
        await manager.wait()
        snapshot = manager.presentation()
        assert snapshot['current_tool'] is None and snapshot['status'] == 'completed'
        assert 'PRIVATE' not in str(snapshot)
    asyncio.run(scenario())
