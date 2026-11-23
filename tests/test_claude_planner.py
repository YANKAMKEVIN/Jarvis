"""Optional Claude planner backend with a fake SDK client (idea 41)."""
import asyncio
from types import SimpleNamespace as NS

import pytest
from livekit.agents import function_tool

from jarvis.planner import AnthropicPlannerModel, PlannerEngine, PlannerModelError, build_planner_model


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **request):
        self.requests.append(request)
        return self.responses.pop(0)


def tool_use():
    return NS(stop_reason="tool_use", content=[
        NS(type="thinking", thinking="", signature="sig"),
        NS(type="text", text="J'ouvre Notes."),
        NS(type="tool_use", id="toolu_1", name="open_app", input={"app_name": "Notes"}),
    ])


def test_backend_selection_and_defaults(monkeypatch):
    monkeypatch.delenv("JARVIS_CLAUDE_PLANNER_MODEL", raising=False)
    model = build_planner_model("claude")
    assert isinstance(model, AnthropicPlannerModel)
    assert model.name == "claude-opus-5-5" and model.effort == "medium"


def test_full_loop_replays_claude_blocks_and_groups_tool_results():
    calls = []

    @function_tool(name="open_app", description="Ouvre une app.")
    async def open_app(app_name: str) -> dict:
        calls.append(app_name)
        return {"ok": True, "state_confirmed": True}

    client = FakeClient([tool_use(), NS(stop_reason="end_turn", content=[NS(type="text", text="Notes est ouverte.")])])
    engine = PlannerEngine(AnthropicPlannerModel(client=client), [open_app])
    outcome = asyncio.run(engine.run("Ouvre Notes"))
    assert outcome.status == "completed" and outcome.summary == "Notes est ouverte." and calls == ["Notes"]
    first, second = client.requests
    assert first["system"].startswith("Tu es le planificateur")
    assert first["fallbacks"] == "default" and first["output_config"] == {"effort": "medium"}
    assert {tool["name"] for tool in first["tools"]} >= {"open_app", "ask_clarification"}
    assert all("input_schema" in tool for tool in first["tools"])
    assistant, results = second["messages"][1], second["messages"][2]
    assert assistant["role"] == "assistant" and assistant["content"][0].type == "thinking"
    assert results["role"] == "user" and results["content"][0]["type"] == "tool_result"
    assert results["content"][0]["tool_use_id"] == "toolu_1"


def test_refusal_and_sdk_errors_become_planner_errors():
    model = AnthropicPlannerModel(client=FakeClient([NS(stop_reason="refusal", content=[])]))
    with pytest.raises(PlannerModelError) as refusal:
        model.complete([{"role": "user", "content": "x"}], [])
    assert refusal.value.code == "model_refusal"

    class Broken:
        beta = NS(messages=NS(create=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))))
    with pytest.raises(PlannerModelError) as failure:
        AnthropicPlannerModel(client=Broken()).complete([{"role": "user", "content": "x"}], [])
    assert failure.value.code == "model_http_error"
