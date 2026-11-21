"""The Mac-only smoke test stays in step with the real tool registry.

scripts/smoke_test.py only runs on a Mac with permissions, so a renamed tool
would surface there as a FAIL long after the change. These checks run
anywhere: every tool the script calls exists, and the planner tasks group
skips cleanly when no brain is available.
"""

import ast
import inspect
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import smoke_test
from jarvis.live.registry import create_live_registry


SCRIPT = Path(smoke_test.__file__)

# Helper -> index of the positional argument holding the tool name.
TOOL_CALLERS = {"call": 1, "call_ok": 1, "call_on": 2, "use": 0}


def tool_names_used_by_script() -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            index = TOOL_CALLERS.get(node.func.id)
            if index is not None and len(node.args) > index:
                arg = node.args[index]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    names.add(arg.value)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            value = node.value
            # ctx.tools["x"] and the local alias t = ctx.tools.
            if (isinstance(value, ast.Attribute) and value.attr == "tools") or (
                    isinstance(value, ast.Name) and value.id == "t"):
                names.add(node.slice.value)
    return names


class SmokeToolNamesTest(unittest.TestCase):
    def test_every_tool_called_by_the_smoke_test_exists(self):
        registry = create_live_registry()
        exposed = {tool.info.name for tool in registry.livekit_tools()}
        used = tool_names_used_by_script()
        # Guards the parser itself: an empty set would pass vacuously.
        self.assertGreater(len(used), 50)
        self.assertTrue({"run_task", "task_status", "cancel_task", "confirm_action",
                         "cancel_action", "enable_safe_mode"} <= used)
        self.assertEqual(sorted(used - exposed), [])

    def test_mission_tools_accept_the_arguments_the_group_passes(self):
        registry = create_live_registry()
        tools = {tool.info.name: tool for tool in registry.livekit_tools()}
        self.assertEqual(
            list(inspect.signature(tools["run_task"]._func).parameters),
            ["goal", "read_only", "after_id"])
        self.assertIn("task_id", inspect.signature(tools["task_status"]._func).parameters)
        self.assertIn("task_id", inspect.signature(tools["cancel_task"]._func).parameters)
        self.assertTrue(registry.planner_tools)


class TasksGroupSkipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ctx = smoke_test.Context(tools={}, workdir=Path(self.tmp.name))

    def never_called(self, *args, **kwargs):
        self.fail("aucune etape ne doit tourner sans planificateur")

    def test_gemini_without_key_is_skipped(self):
        env = {"JARVIS_PLANNER_BACKEND": "gemini"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("GOOGLE_API_KEY", None)
            with self.assertRaises(smoke_test.Skipped) as raised:
                smoke_test.group_tasks(self.ctx, self.never_called)
        self.assertIn("GOOGLE_API_KEY", str(raised.exception))

    def test_unreachable_ollama_is_skipped(self):
        env = {"JARVIS_PLANNER_BACKEND": "ollama",
               "JARVIS_OLLAMA_URL": "http://127.0.0.1:9/api/chat"}
        with mock.patch.dict(os.environ, env):
            with self.assertRaises(smoke_test.Skipped) as raised:
                smoke_test.group_tasks(self.ctx, self.never_called)
        self.assertIn("Ollama injoignable (http://127.0.0.1:9/api/tags)", str(raised.exception))

    def test_runner_records_a_skip_not_a_failure(self):
        env = {"JARVIS_PLANNER_BACKEND": "gemini"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("GOOGLE_API_KEY", None)
            with redirect_stdout(io.StringIO()):
                smoke_test.run_group(self.ctx, "tasks")
        self.assertEqual([r.status for r in self.ctx.results], ["skip"])
        self.assertFalse(any(Path(self.tmp.name).iterdir()), "rien ne doit etre cree")


class OnDemandGroupsTest(unittest.TestCase):
    def test_tasks_only_runs_when_named(self):
        self.assertIn("tasks", smoke_test.GROUPS)
        self.assertEqual(smoke_test.ON_DEMAND, {"tasks"})
        out = io.StringIO()
        with mock.patch("sys.argv", ["smoke_test.py", "--list"]), redirect_stdout(out):
            self.assertEqual(smoke_test.main(), 0)
        self.assertIn("tasks (sur demande : --group tasks)", out.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
