"""Live POC: window and file tools."""
import asyncio
import unittest
from unittest.mock import patch

from jarvis.live.tools import create_live_tools
from live_poc_fakes_core import RecordingLiveSecurity
from live_poc_fakes_input import RecordingLiveFileSystemTools
from live_poc_fakes_macos import RecordingLiveMacOSTools


class LiveWindowToolTest(unittest.TestCase):
    def make_tools(self, security=None, macos_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            macos_tools=macos_tools or RecordingLiveMacOSTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_get_active_window_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["get_active_window"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "get_active_window")
        self.assertEqual(result["target_app"], "Safari")
        self.assertEqual(result["window_title"], "Example")
        self.assertEqual(macos_tools.active_window_calls, 1)

    def test_focus_window_success_uses_security_and_backend(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["focus_window"]

        result = asyncio.run(tool("Safari"))

        self.assertTrue(result["ok"])
        self.assertEqual(security.intents[0].action, "focus_window")
        self.assertEqual(macos_tools.focus_window_calls, ["Safari"])

    def test_minimize_window_can_target_active_window(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["minimize_window"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(security.intents[0].action, "minimize_window")
        self.assertEqual(macos_tools.minimize_window_calls, [None])

    def test_maximize_window_uses_backend_without_fullscreen_claim(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["maximize_window"]

        result = asyncio.run(tool("Visual Studio Code"))

        self.assertTrue(result["ok"])
        self.assertEqual(macos_tools.maximize_window_calls, ["Visual Studio Code"])

    def test_move_window_success_passes_position_and_app_name(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["move_window"]

        result = asyncio.run(tool("left", "Safari"))

        self.assertTrue(result["ok"])
        self.assertEqual(macos_tools.move_window_calls, [("left", "Safari")])

    def test_move_window_invalid_position_is_rejected_before_backend(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["move_window"]

        result = asyncio.run(tool("top", "Safari"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "La position doit etre left, right, center ou fullscreen.")
        self.assertEqual(security.intents, [])
        self.assertEqual(macos_tools.move_window_calls, [])

    def test_window_tool_failure_returns_explicit_failure(self):
        macos_tools = RecordingLiveMacOSTools(
            window_error=RuntimeError("System Events erreur -10827"),
        )
        tool = self.make_tools(macos_tools=macos_tools)["get_active_window"]

        result = asyncio.run(tool())

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "get_active_window")
        self.assertIn("-10827", result["message"])

    def test_state_confirmed_false_survives_to_livekit_dict(self):
        macos_tools = RecordingLiveMacOSTools(
            window_state={
                "target_app": "Safari",
                "frontmost": True,
                "window_title": "Example",
                "position": {"x": 100, "y": 100},
                "size": {"width": 600, "height": 400},
                "minimized": False,
                "fullscreen": False,
                "command_executed": True,
                "state_confirmed": False,
                "previous_position": {"x": 100, "y": 100},
                "previous_size": {"width": 600, "height": 400},
            }
        )
        tool = self.make_tools(macos_tools=macos_tools)["move_window"]

        result = asyncio.run(tool("left", "Safari"))

        self.assertTrue(result["ok"])
        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertIn("pas pu confirmer", result["message"])

    def test_window_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["get_active_window"].info.name, "get_active_window")
        self.assertIn("fenetre active", tools["get_active_window"].info.description.lower())
        self.assertEqual(tools["focus_window"].info.name, "focus_window")
        self.assertIn("premier plan", tools["focus_window"].info.description.lower())
        self.assertEqual(tools["minimize_window"].info.name, "minimize_window")
        self.assertIn("minimise", tools["minimize_window"].info.description.lower())
        self.assertEqual(tools["maximize_window"].info.name, "maximize_window")
        self.assertIn("sans activer", tools["maximize_window"].info.description.lower())
        self.assertEqual(tools["move_window"].info.name, "move_window")
        self.assertIn("left", tools["move_window"].info.description.lower())

    def test_window_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["get_active_window"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_window_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["move_window"]
            result = asyncio.run(tool("center", "Safari"))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("move_window", ("center", "Safari"))])

    def test_existing_capability_tools_remain_exposed(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("play_pause", tools)
        self.assertIn("get_battery_status", tools)


class LiveFilesToolTest(unittest.TestCase):
    def make_tools(self, security=None, filesystem_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            filesystem_tools=filesystem_tools or RecordingLiveFileSystemTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_list_files_success_returns_structured_result(self):
        filesystem_tools = RecordingLiveFileSystemTools()
        tool = self.make_tools(filesystem_tools=filesystem_tools)["list_files"]

        result = asyncio.run(tool("Documents"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "list_files")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(filesystem_tools.calls, [("list_files", "Documents")])

    def test_find_files_success_returns_structured_result(self):
        filesystem_tools = RecordingLiveFileSystemTools()
        tool = self.make_tools(filesystem_tools=filesystem_tools)["find_files"]

        result = asyncio.run(tool("report", "Downloads"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "find_files")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(
            filesystem_tools.calls,
            [("find_files", "report", "Downloads")],
        )

    def test_get_file_info_success_returns_structured_result(self):
        filesystem_tools = RecordingLiveFileSystemTools()
        tool = self.make_tools(filesystem_tools=filesystem_tools)["get_file_info"]

        result = asyncio.run(tool("/Users/test/report.pdf"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "file")
        self.assertEqual(result["size_bytes"], 42)
        self.assertEqual(
            filesystem_tools.calls,
            [("get_file_info", "/Users/test/report.pdf")],
        )

    def test_open_file_and_folder_preserve_unconfirmed_state(self):
        filesystem_tools = RecordingLiveFileSystemTools()
        tools = self.make_tools(filesystem_tools=filesystem_tools)

        file_result = asyncio.run(tools["open_file"]("/Users/test/report.pdf"))
        folder_result = asyncio.run(tools["open_folder"]("/Users/test/Documents"))

        self.assertTrue(file_result["command_executed"])
        self.assertFalse(file_result["state_confirmed"])
        self.assertTrue(folder_result["command_executed"])
        self.assertFalse(folder_result["state_confirmed"])

    def test_create_rename_and_move_files_use_security(self):
        security = RecordingLiveSecurity()
        filesystem_tools = RecordingLiveFileSystemTools()
        tools = self.make_tools(
            security=security,
            filesystem_tools=filesystem_tools,
        )

        create = asyncio.run(tools["create_folder"]("/Users/test/New"))
        rename = asyncio.run(
            tools["rename_file"]("/Users/test/old.txt", "new.txt")
        )
        move = asyncio.run(
            tools["move_file"]("/Users/test/new.txt", "/Users/test/Done/new.txt")
        )

        self.assertTrue(create["state_confirmed"])
        self.assertTrue(rename["state_confirmed"])
        self.assertTrue(move["state_confirmed"])
        self.assertEqual(
            [intent.action for intent in security.intents],
            ["create_folder", "rename_file", "move_file"],
        )

    def test_files_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["list_files"].info.name, "list_files")
        self.assertIn("dossier", tools["list_files"].info.description.lower())
        self.assertEqual(tools["find_files"].info.name, "find_files")
        self.assertIn("extension", tools["find_files"].info.description.lower())
        self.assertEqual(tools["get_file_info"].info.name, "get_file_info")
        self.assertIn("taille", tools["get_file_info"].info.description.lower())
        self.assertEqual(tools["open_file"].info.name, "open_file")
        self.assertEqual(tools["open_folder"].info.name, "open_folder")
        self.assertEqual(tools["create_folder"].info.name, "create_folder")
        self.assertEqual(tools["rename_file"].info.name, "rename_file")
        self.assertEqual(tools["move_file"].info.name, "move_file")

    def test_file_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["list_files"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_files_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["move_file"]
            result = asyncio.run(tool("/Users/test/a.txt", "/Users/test/b.txt"))

        self.assertTrue(result["ok"])
        self.assertEqual(
            calls,
            [("move_file", ("/Users/test/a.txt", "/Users/test/b.txt"))],
        )

    def test_existing_capability_tools_remain_exposed_with_files(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("play_pause", tools)
        self.assertIn("get_battery_status", tools)
        self.assertIn("get_active_window", tools)
