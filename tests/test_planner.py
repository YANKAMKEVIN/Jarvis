import asyncio
import io
import json
import threading
import unittest
import urllib.error

from livekit.agents import function_tool

from jarvis.live.registry import create_live_tools
from jarvis.planner import (
    PLANNER_TOOL_NAMES,
    ModelTurn,
    OllamaPlannerModel,
    PlannerEngine,
    PlannerModelError,
    ScriptedModel,
    ToolCall,
)


class FakeTools:
    """Real LiveKit function tools (schemas included) backed by recorders."""

    def __init__(self, open_app_ok=True):
        self.calls = []
        self.open_app_ok = open_app_ok

        @function_tool(name="open_app", description="Ouvre une app.")
        async def open_app(app_name: str) -> dict:
            self.calls.append(("open_app", app_name))
            if self.open_app_ok:
                return {"ok": True, "state_confirmed": True, "app": app_name}
            return {"ok": False, "error_code": "app_not_found", "message": "introuvable"}

        @function_tool(name="get_active_window", description="Fenetre active.")
        async def get_active_window() -> dict:
            self.calls.append(("get_active_window",))
            return {"ok": True, "target_app": "Safari", "big": "x" * 5000}

        @function_tool(name="prepare_send_message", description="Prepare un envoi.")
        async def prepare_send_message(app_name: str, text: str) -> dict:
            self.calls.append(("prepare_send_message", app_name))
            return {"ok": True, "requires_confirmation": True, "token": "tok123",
                    "target_app": app_name}

        @function_tool(name="confirm_action", description="Confirme.")
        async def confirm_action(token: str) -> dict:
            self.calls.append(("confirm_action", token))
            return {"ok": True}

        self.tools = [open_app, get_active_window, prepare_send_message, confirm_action]


def call(name, **arguments):
    return ToolCall(id=f"c_{name}", name=name, arguments=arguments)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def run(engine, goal="Ouvre Safari", cancel=None):
    return asyncio.run(engine.run(goal, cancel))


class PlannerEngineTest(unittest.TestCase):
    def test_runs_tools_then_completes_with_model_summary(self):
        fake = FakeTools()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("open_app", app_name="Safari")]),
            ModelTurn(text="Safari est ouvert."),
        ])

        outcome = run(PlannerEngine(model, fake.tools))

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.summary, "Safari est ouvert.")
        self.assertEqual(fake.calls, [("open_app", "Safari")])
        self.assertEqual(outcome.to_dict()["steps"], [
            {"tool": "open_app", "ok": True, "state_confirmed": True},
        ])

    def test_tool_results_are_fed_back_to_the_model(self):
        fake = FakeTools()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("open_app", app_name="Safari")]),
            ModelTurn(text="ok"),
        ])

        run(PlannerEngine(model, fake.tools))

        second_call = model.calls[1]
        self.assertEqual(second_call[0]["role"], "system")
        self.assertEqual(second_call[1], {"role": "user", "content": "Ouvre Safari"})
        tool_message = second_call[-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertEqual(tool_message["name"], "open_app")
        self.assertEqual(json.loads(tool_message["content"])["app"], "Safari")

    def test_outward_action_pauses_for_user_confirmation(self):
        fake = FakeTools()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("prepare_send_message", app_name="WhatsApp", text="Salut")]),
            ModelTurn(text="ne doit jamais etre atteint"),
        ])

        outcome = run(PlannerEngine(model, fake.tools))

        self.assertEqual(outcome.status, "needs_confirmation")
        self.assertEqual(outcome.pending, {
            "token": "tok123", "tool": "prepare_send_message", "target_app": "WhatsApp",
            "arguments": {"app_name": "WhatsApp", "text": "Salut"},
        })
        self.assertEqual(len(model.calls), 1)  # stopped right after preparing
        self.assertNotIn(("confirm_action", "tok123"), fake.calls)

    def test_planner_can_never_confirm_an_action(self):
        fake = FakeTools()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("confirm_action", token="tok123")]),
            ModelTurn(text="fin"),
        ])

        outcome = run(PlannerEngine(model, fake.tools))

        self.assertEqual(fake.calls, [])
        self.assertEqual(outcome.steps[0].error_code, "tool_not_allowed")
        self.assertNotIn("confirm_action", [s["function"]["name"] for s in PlannerEngine(model, fake.tools).schemas])

    def test_invalid_arguments_are_reported_not_raised(self):
        fake = FakeTools()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("open_app", nom="Safari")]),
            ModelTurn(tool_calls=[ToolCall("c", "open_app", {"__invalid_json__": "{"})]),
            ModelTurn(text="fin"),
        ])

        outcome = run(PlannerEngine(model, fake.tools))

        self.assertEqual([s.error_code for s in outcome.steps], ["invalid_arguments", "invalid_arguments"])
        self.assertEqual(outcome.status, "completed")

    def test_stops_after_consecutive_failures(self):
        fake = FakeTools(open_app_ok=False)
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("open_app", app_name="X")]) for _ in range(5)
        ])

        outcome = run(PlannerEngine(model, fake.tools, max_consecutive_failures=3))

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(len(fake.calls), 3)
        self.assertIn("app_not_found", outcome.summary)

    def test_success_resets_the_failure_counter(self):
        fake = FakeTools()
        turns = [
            ModelTurn(tool_calls=[call("open_app", nom="bad")]),
            ModelTurn(tool_calls=[call("open_app", nom="bad")]),
            ModelTurn(tool_calls=[call("open_app", app_name="Safari")]),
            ModelTurn(tool_calls=[call("open_app", nom="bad")]),
            ModelTurn(tool_calls=[call("open_app", nom="bad")]),
            ModelTurn(text="fin"),
        ]

        outcome = run(PlannerEngine(ScriptedModel(turns), fake.tools, max_consecutive_failures=3))

        self.assertEqual(outcome.status, "completed")

    def test_step_budget(self):
        fake = FakeTools()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("get_active_window")]) for _ in range(10)
        ])

        outcome = run(PlannerEngine(model, fake.tools, max_steps=4))

        self.assertEqual(outcome.status, "budget_exceeded")
        self.assertEqual(len(outcome.steps), 4)

    def test_time_budget(self):
        fake = FakeTools()
        clock = FakeClock()

        def slow_turn(messages):
            clock.now += 100
            return ModelTurn(tool_calls=[call("get_active_window")])

        model = ScriptedModel([slow_turn, slow_turn, slow_turn])

        outcome = run(PlannerEngine(model, fake.tools, max_seconds=150, clock=clock))

        self.assertEqual(outcome.status, "budget_exceeded")
        self.assertIn("150 secondes", outcome.summary)

    def test_cancel_between_steps(self):
        fake = FakeTools()
        cancel = threading.Event()

        def cancelling_turn(messages):
            cancel.set()
            return ModelTurn(tool_calls=[call("open_app", app_name="Safari")])

        outcome = run(PlannerEngine(ScriptedModel([cancelling_turn]), fake.tools), cancel=cancel)

        self.assertEqual(outcome.status, "cancelled")
        self.assertEqual(fake.calls, [])  # cancelled before executing

    def test_model_errors_end_the_task_cleanly(self):
        class Down:
            name = "down"

            def complete(self, messages, tools):
                raise PlannerModelError("Ollama injoignable.", "model_unreachable")

        outcome = run(PlannerEngine(Down(), FakeTools().tools))

        self.assertEqual(outcome.status, "failed")
        self.assertIn("injoignable", outcome.summary)

    def test_empty_goal(self):
        outcome = run(PlannerEngine(ScriptedModel([]), FakeTools().tools), goal="  ")

        self.assertEqual(outcome.status, "failed")

    def test_long_tool_results_are_truncated(self):
        fake = FakeTools()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("get_active_window")]),
            ModelTurn(text="fin"),
        ])

        run(PlannerEngine(model, fake.tools))

        content = model.calls[1][-1]["content"]
        self.assertLess(len(content), 1300)
        self.assertTrue(content.endswith("(tronque)"))

    def test_real_registry_allowlist(self):
        engine = PlannerEngine(ScriptedModel([]), create_live_tools())
        exposed = set(engine.tools)

        self.assertEqual(exposed, set(PLANNER_TOOL_NAMES))
        for forbidden in ("confirm_action", "cancel_action", "lock_screen", "click",
                          "type_text", "hotkey", "remember", "forget", "propose_memory"):
            self.assertNotIn(forbidden, exposed)
        names = [schema["function"]["name"] for schema in engine.schemas]
        self.assertEqual(names, sorted(names))  # stable prompt prefix


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class OllamaPlannerModelTest(unittest.TestCase):
    def make(self, body=None, error=None):
        self.requests = []

        def opener(request, timeout):
            self.requests.append(json.loads(request.data.decode("utf-8")))
            if error is not None:
                raise error
            return FakeResponse(json.dumps(body).encode("utf-8"))

        return OllamaPlannerModel(model="granite4:3b", url="http://x/api/chat", opener=opener)

    def test_parses_tool_calls_and_sends_tools_and_context_size(self):
        model = self.make({"message": {"content": "", "tool_calls": [
            {"function": {"name": "open_app", "arguments": {"app_name": "Safari"}}},
            {"function": {"name": "get_volume", "arguments": "{}"}},
        ]}})
        schema = [{"type": "function", "function": {"name": "open_app"}}]

        turn = model.complete([{"role": "user", "content": "go"}], schema)

        self.assertEqual([(c.name, c.arguments) for c in turn.tool_calls],
                         [("open_app", {"app_name": "Safari"}), ("get_volume", {})])
        sent = self.requests[0]
        self.assertEqual(sent["tools"], schema)
        self.assertEqual(sent["options"]["num_ctx"], 8192)
        self.assertEqual(sent["options"]["temperature"], 0)
        self.assertFalse(sent["stream"])

    def test_converts_history_to_ollama_format(self):
        model = self.make({"message": {"content": "fini"}})
        history = [
            {"role": "system", "content": "s"},
            {"role": "assistant", "content": "", "tool_calls": [call("open_app", app_name="Safari")]},
            {"role": "tool", "name": "open_app", "tool_call_id": "c", "content": "{}"},
        ]

        turn = model.complete(history, [])

        self.assertEqual(turn.text, "fini")
        sent = self.requests[0]["messages"]
        self.assertEqual(sent[1]["tool_calls"],
                         [{"function": {"name": "open_app", "arguments": {"app_name": "Safari"}}}])
        self.assertEqual(sent[2], {"role": "tool", "content": "{}", "tool_name": "open_app"})

    def test_invalid_json_arguments_are_flagged(self):
        model = self.make({"message": {"tool_calls": [
            {"function": {"name": "open_app", "arguments": "{oops"}},
        ]}})

        turn = model.complete([], [])

        self.assertIn("__invalid_json__", turn.tool_calls[0].arguments)

    def test_unreachable_and_error_responses(self):
        down = self.make(error=urllib.error.URLError("refused"))
        with self.assertRaises(PlannerModelError) as context:
            down.complete([], [])
        self.assertEqual(context.exception.code, "model_unreachable")

        failing = self.make({"error": "model not found"})
        with self.assertRaises(PlannerModelError):
            failing.complete([], [])


if __name__ == "__main__":
    unittest.main()
