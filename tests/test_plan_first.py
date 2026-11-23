"""Option « montre-moi le plan avant d'agir » (idea 42)."""
import asyncio

from jarvis.live.registry import create_live_registry
from jarvis.planner import ModelTurn, ScriptedModel


class FakeMemory:
    def resolve_person(self, name, app_name=None): return None
    def log_action(self, *args, **kwargs): return None
    def recent_missions(self, *args, **kwargs): return []
    def record_mission(self, *args, **kwargs): return None


def registry(turns, plan_first=True):
    r = create_live_registry(memory_capability=FakeMemory(), planner_model=ScriptedModel(turns))
    r.plan_first = plan_first
    return r, {tool.info.name: tool for tool in r.livekit_tools()}


def test_plan_is_shown_and_nothing_runs_before_the_yes():
    r, tools = registry([ModelTurn(text="1. Ouvrir Finder\n2. Ranger les PDF"), ModelTurn(text="Fait.")])

    async def scenario():
        prepared = await tools["run_task"]("Range mes PDF")
        assert r.tasks.status().get("running") in (False, None) or "missions" in r.tasks.status()
        r.note_user_turn()
        confirmed = await tools["confirm_action"](prepared["token"])
        await asyncio.sleep(0.05)
        await r.aclose()
        return prepared, confirmed
    prepared, confirmed = asyncio.run(scenario())
    assert prepared["requires_confirmation"] is True and "Ranger les PDF" in prepared["plan"]
    assert confirmed["ok"] is True and confirmed.get("task_started") is True


def test_cancel_drops_the_mission_and_default_is_off(monkeypatch):
    r, tools = registry([ModelTurn(text="1. Etape")])

    async def scenario():
        prepared = await tools["run_task"]("Range mes PDF")
        cancelled = await tools["cancel_action"](prepared["token"])
        await r.aclose()
        return cancelled
    assert asyncio.run(scenario())["cancelled"] is True

    monkeypatch.delenv("JARVIS_PLAN_FIRST", raising=False)
    r, tools = registry([ModelTurn(text="Fait.")], plan_first=None)

    async def direct():
        started = await tools["run_task"]("Range mes PDF")
        await r.aclose()
        return started
    started = asyncio.run(direct())
    assert started.get("task_started") is True and "requires_confirmation" not in started


def test_research_missions_never_wait_for_a_plan():
    r, tools = registry([ModelTurn(text="Fait.")])

    async def scenario():
        started = await tools["run_task"]("Cherche la météo", read_only=True)
        await r.aclose()
        return started
    assert asyncio.run(scenario()).get("task_started") is True
