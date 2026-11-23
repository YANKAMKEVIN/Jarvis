"""A stuck tool fails its step instead of the whole mission (idea 39)."""
import asyncio

from livekit.agents import function_tool

from jarvis.planner import ModelTurn, PlannerEngine, ScriptedModel, ToolCall


def tools(calls):
    @function_tool(name="get_active_window", description="Fenetre active.")
    async def get_active_window() -> dict:
        calls.append("get_active_window")
        await asyncio.sleep(10)
        return {"ok": True}

    @function_tool(name="open_app", description="Ouvre une app.")
    async def open_app(app_name: str) -> dict:
        calls.append("open_app")
        return {"ok": True, "state_confirmed": True}

    return [get_active_window, open_app]


def test_stuck_tool_times_out_then_the_mission_continues():
    calls = []
    seen = []

    def after_timeout(messages):
        seen.append(messages[-1]["content"])
        return ModelTurn(tool_calls=[ToolCall(id="2", name="open_app", arguments={"app_name": "Notes"})])

    model = ScriptedModel([
        ModelTurn(tool_calls=[ToolCall(id="1", name="get_active_window", arguments={})]),
        after_timeout,
        ModelTurn(text="Notes ouverte."),
    ])
    engine = PlannerEngine(model, tools(calls), step_timeout=0.05)
    outcome = asyncio.run(engine.run("Ouvre Notes"))
    assert outcome.status == "completed"
    assert [step.tool for step in outcome.steps] == ["get_active_window", "open_app"]
    assert outcome.steps[0].ok is False and outcome.steps[0].error_code == "tool_timeout"
    assert "tool_timeout" in seen[0]


def test_slow_tools_get_their_own_longer_limit():
    engine = PlannerEngine(ScriptedModel([]), [], step_timeout=1)
    assert engine.tool_timeouts["web_answer"] > engine.step_timeout
    custom = PlannerEngine(ScriptedModel([]), [], tool_timeouts={})
    assert custom.tool_timeouts == {}
