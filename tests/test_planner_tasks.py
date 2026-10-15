import asyncio
import tempfile
import threading
import unittest
from pathlib import Path

from jarvis.capabilities.memory import MemoryCapability
from jarvis.capabilities.results import ToolResult
from jarvis.live import agent
from jarvis.live.registry import create_live_registry
from jarvis.memory.store import MemoryStore
from jarvis.planner import ModelTurn, PlannerEngine, ScriptedModel, TaskOutcome, ToolCall
from jarvis.planner.engine import StepRecord
from jarvis.planner.tasks import TaskManager, announcement_for


def call(name, **arguments):
    return ToolCall(id=f"c_{name}", name=name, arguments=arguments)


class RecordingInteraction:
    def __init__(self):
        self.calls = []

    def focus_app_ui_and_type(self, *args):
        self.calls.append(args)
        return ToolResult.success(action="focus_app_ui_and_type", message="ok")


class RecordingMessaging:
    def composer_query(self, app_name):
        return None

    def supports_composer_send(self, app_name):
        return False

    def ensure_recipient(self, app_name, recipient):
        return ToolResult.success(action="verify_recipient", message="ok")


class RecordingApps:
    def __init__(self):
        self.calls = []

    def is_app_running(self, app_name):
        self.calls.append(app_name)
        return ToolResult.success(action="is_app_running", message="ok", running=True)


def make_registry(model, tempdir, **kwargs):
    memory = MemoryCapability(MemoryStore(Path(tempdir) / "memory.db"))
    registry = create_live_registry(
        planner_model=model,
        memory_capability=memory,
        interaction_capability=kwargs.get("interaction", RecordingInteraction()),
        messaging_capability=RecordingMessaging(),
        app_capability=kwargs.get("apps", RecordingApps()),
    )
    tools = {tool.info.name: tool for tool in registry.livekit_tools()}
    return registry, tools, memory


class TaskManagerTest(unittest.TestCase):
    def make_manager(self, turns, finished=None):
        self.finished = finished if finished is not None else []

        async def on_finished(goal, outcome):
            self.finished.append((goal, outcome))

        return TaskManager(
            lambda: PlannerEngine(ScriptedModel(turns), []),
            on_finished=on_finished,
        )

    def test_start_returns_immediately_then_announces(self):
        manager = self.make_manager([ModelTurn(text="Fait.")])

        async def scenario():
            started = manager.start("Fais quelque chose")
            self.assertTrue(manager.running or manager._task is not None)
            outcome = await manager.wait()
            return started, outcome

        started, outcome = asyncio.run(scenario())

        self.assertTrue(started["task_started"])
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(self.finished[0][0], "Fais quelque chose")
        self.assertEqual(manager.status()["last_task"]["summary"], "Fait.")

    def test_only_one_task_at_a_time_and_status_while_running(self):
        release = threading.Event()

        def blocking(messages):
            release.wait(5)
            return ModelTurn(text="fini")

        manager = self.make_manager([blocking])

        async def scenario():
            manager.start("tache 1")
            await asyncio.sleep(0.05)
            second = manager.start("tache 2")
            status = manager.status()
            release.set()
            await manager.wait()
            return second, status

        second, status = asyncio.run(scenario())

        self.assertEqual(second["error_code"], "task_already_running")
        self.assertTrue(status["running"])
        self.assertEqual(status["goal"], "tache 1")
        self.assertEqual(manager.status()["running"], False)

    def test_cancel_stops_the_task(self):
        release = threading.Event()

        def blocking(messages):
            release.wait(5)
            return ModelTurn(tool_calls=[call("open_app", app_name="Safari")])

        manager = self.make_manager([blocking])

        async def scenario():
            manager.start("tache")
            await asyncio.sleep(0.05)
            requested = manager.cancel()
            release.set()
            return requested, await manager.wait()

        requested, outcome = asyncio.run(scenario())

        self.assertTrue(requested["cancel_requested"])
        self.assertEqual(outcome.status, "cancelled")
        self.assertFalse(manager.cancel()["cancel_requested"])

    def test_invalid_goals(self):
        manager = self.make_manager([])

        async def scenario():
            return manager.start("  "), manager.start("x" * 501)

        empty, too_long = asyncio.run(scenario())

        self.assertEqual(empty["error_code"], "invalid_goal")
        self.assertEqual(too_long["error_code"], "goal_too_long")
        self.assertEqual(manager.status()["message"], "Aucune tache lancee.")

    def test_engine_creation_failure_becomes_a_failed_outcome(self):
        def broken():
            raise RuntimeError("boom")

        finished = []

        async def on_finished(goal, outcome):
            finished.append(outcome)

        manager = TaskManager(broken, on_finished=on_finished)

        async def scenario():
            manager.start("tache")
            return await manager.wait()

        outcome = asyncio.run(scenario())

        self.assertEqual(outcome.status, "failed")
        self.assertIn("boom", outcome.summary)
        self.assertEqual(len(finished), 1)


class AnnouncementTest(unittest.TestCase):
    def test_confirmation_announcement_carries_details_and_token(self):
        outcome = TaskOutcome("needs_confirmation", "x", pending={
            "token": "tok1", "tool": "prepare_send_message", "target_app": "WhatsApp",
            "arguments": {"app_name": "WhatsApp", "recipient": "Paul", "text": "J'arrive"},
        })

        text = announcement_for("previens Paul", outcome)

        for expected in ("PREPARE", "WhatsApp", "Paul", "J'arrive", 'confirm_action(token="tok1")',
                         'cancel_action(token="tok1")'):
            self.assertIn(expected, text)

    def test_other_statuses(self):
        self.assertIn("terminee", announcement_for("g", TaskOutcome("completed", "Dossier cree.")))
        self.assertIn("annulee", announcement_for("g", TaskOutcome("cancelled", "")))
        failed = announcement_for("g", TaskOutcome("budget_exceeded", "Arret apres 25 etapes."))
        self.assertIn("n'a pas abouti", failed)
        self.assertIn("25 etapes", failed)


class RegistryTaskToolsTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_task_tools_are_exposed(self):
        _, tools, _ = make_registry(ScriptedModel([]), self.tempdir.name)

        for name in ("run_task", "task_status", "cancel_task"):
            self.assertIn(name, tools)
        self.assertIn("TACHE LONGUE", tools["run_task"].info.description)

    def test_run_task_uses_registry_tools_and_announces(self):
        apps = RecordingApps()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("is_app_running", app_name="Safari")]),
            ModelTurn(text="Safari tourne."),
        ])
        registry, tools, memory = make_registry(model, self.tempdir.name, apps=apps)
        spoken = []

        async def notifier(instructions):
            spoken.append(instructions)

        registry.set_task_notifier(notifier)

        async def scenario():
            started = await tools["run_task"]("Verifie si Safari tourne")
            await registry.tasks.wait()
            return started

        started = asyncio.run(scenario())

        self.assertTrue(started["task_started"])
        self.assertEqual(apps.calls, ["Safari"])
        self.assertEqual(len(spoken), 1)
        self.assertIn("Safari tourne.", spoken[0])
        journal = [e.tool for e in memory.store.recent_episodes()]
        self.assertIn("task_completed", journal)
        self.assertIn("run_task", journal)

    def test_message_prepared_by_a_task_is_confirmable_by_voice(self):
        interaction = RecordingInteraction()
        model = ScriptedModel([
            ModelTurn(tool_calls=[call("prepare_send_message", app_name="WhatsApp",
                                       text="J'arrive", recipient="Paul")]),
        ])
        registry, tools, _ = make_registry(model, self.tempdir.name, interaction=interaction)
        spoken = []

        async def notifier(instructions):
            spoken.append(instructions)

        registry.set_task_notifier(notifier)

        async def scenario():
            await tools["run_task"]("Previens Paul que j'arrive")
            outcome = await registry.tasks.wait()
            self.assertEqual(interaction.calls, [])  # nothing sent by the task
            confirmed = await tools["confirm_action"](outcome.pending["token"])
            return outcome, confirmed

        outcome, confirmed = asyncio.run(scenario())

        self.assertEqual(outcome.status, "needs_confirmation")
        self.assertIn(outcome.pending["token"], spoken[0])
        self.assertTrue(confirmed["ok"])
        self.assertEqual(interaction.calls[0][:2], ("WhatsApp", "J'arrive"))

    def test_status_and_cancel_tools(self):
        _, tools, _ = make_registry(ScriptedModel([]), self.tempdir.name)

        async def scenario():
            return await tools["task_status"](), await tools["cancel_task"]()

        status, cancel = asyncio.run(scenario())

        self.assertFalse(status["running"])
        self.assertFalse(cancel["cancel_requested"])


class FakeSession:
    def __init__(self):
        self.replies = []

    def generate_reply(self, **kwargs):
        self.replies.append(kwargs)


class FakeAgentBase:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class AgentAnnouncementTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def make_assistant(self, base):
        factory = lambda: create_live_registry(
            memory_capability=MemoryCapability(MemoryStore(Path(self.tempdir.name) / "m.db")),
        )
        return agent.create_assistant_class(base, registry_factory=factory)()

    def test_registry_notifier_speaks_through_the_session(self):
        class WithSession(FakeAgentBase):
            session = FakeSession()

        assistant = self.make_assistant(WithSession)

        asyncio.run(assistant.registry.task_notifier("Annonce"))

        self.assertEqual(WithSession.session.replies, [{"instructions": "Annonce"}])
        self.assertIn("run_task", [t.info.name for t in assistant.kwargs["tools"]])

    def test_announcement_without_session_is_dropped_safely(self):
        class NoSession(FakeAgentBase):
            @property
            def session(self):
                raise RuntimeError("no session")

        assistant = self.make_assistant(NoSession)

        asyncio.run(assistant.announce("Annonce"))  # must not raise


class LastCompletedTest(unittest.TestCase):
    def manager(self):
        return TaskManager(lambda: PlannerEngine(ScriptedModel([]), []))

    def test_returns_goal_and_ok_tool_names(self):
        mgr = self.manager()
        mgr._goal = "préparer réunion"
        mgr._outcome = TaskOutcome("completed", "ok", steps=[
            StepRecord("open_app", True),
            StepRecord("get_volume", False),  # failed step dropped
            StepRecord("browse_open_url", True),
        ])

        self.assertEqual(
            mgr.last_completed(), ("préparer réunion", ["open_app", "browse_open_url"])
        )

    def test_none_when_last_task_failed(self):
        mgr = self.manager()
        mgr._goal = "x"
        mgr._outcome = TaskOutcome("failed", "ko", steps=[StepRecord("open_app", True)])
        self.assertIsNone(mgr.last_completed())

    def test_none_when_no_ok_steps(self):
        mgr = self.manager()
        mgr._goal = "x"
        mgr._outcome = TaskOutcome("completed", "ok", steps=[StepRecord("open_app", False)])
        self.assertIsNone(mgr.last_completed())


class ProcedureToolTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tempdir.cleanup()

    def build(self, model=None):
        model = model or ScriptedModel([ModelTurn(text="ok")])
        registry, tools, memory = make_registry(model, self.tempdir.name)
        return registry, tools, memory

    def test_save_task_procedure_learns_last_task(self):
        registry, tools, memory = self.build()
        registry.tasks._goal = "préparer réunion"
        registry.tasks._outcome = TaskOutcome("completed", "ok", steps=[
            StepRecord("open_app", True),
            StepRecord("browse_open_url", True),
        ])

        result = asyncio.run(tools["save_task_procedure"]("préparer réunion"))

        self.assertTrue(result["ok"])
        got = memory.get_procedure("preparer reunion")
        self.assertEqual(
            [s["tool"] for s in got.data["procedure"]["steps"]],
            ["open_app", "browse_open_url"],
        )

    def test_save_without_completed_task_refuses(self):
        _registry, tools, memory = self.build()

        result = asyncio.run(tools["save_task_procedure"]("vide"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "no_completed_task")

    def test_run_procedure_seeds_task_with_skeleton(self):
        registry, tools, memory = self.build(ScriptedModel([ModelTurn(text="ok")]))
        memory.save_procedure("préparer réunion", [
            {"tool": "open_app", "target": None},
            {"tool": "browse_open_url", "target": None},
        ], source="user")

        async def scenario():
            started = await tools["run_procedure"]("préparer réunion")
            await registry.tasks.wait()
            return started

        started = asyncio.run(scenario())

        self.assertTrue(started["task_started"])
        self.assertIn("open_app", registry.tasks._goal)
        self.assertIn("browse_open_url", registry.tasks._goal)

    def test_run_unknown_procedure_refuses_without_starting(self):
        registry, tools, _memory = self.build()

        result = asyncio.run(tools["run_procedure"]("inconnue"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "memory_not_found")
        self.assertFalse(registry.tasks.running)


if __name__ == "__main__":
    unittest.main()
