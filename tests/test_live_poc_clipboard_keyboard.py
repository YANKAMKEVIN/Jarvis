"""Live POC: clipboard and keyboard tools."""
import asyncio
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis.live.tools import ToolRegistry, create_live_tools
from live_poc_fakes_core import RecordingLiveSecurity
from live_poc_fakes_input import (
    RecordingLiveClipboardTools,
    RecordingLiveKeyboardCapability,
)


class LiveClipboardToolTest(unittest.TestCase):
    def make_tools(self, security=None, clipboard_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            clipboard_tools=clipboard_tools or RecordingLiveClipboardTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_get_clipboard_text_success_returns_structured_result(self):
        clipboard_tools = RecordingLiveClipboardTools()
        tool = self.make_tools(clipboard_tools=clipboard_tools)["get_clipboard_text"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "get_clipboard_text")
        self.assertEqual(result["text"], "Bonjour")
        self.assertEqual(result["length"], 7)
        self.assertEqual(clipboard_tools.calls, [("get_text",)])

    def test_set_clipboard_text_success_uses_security_and_backend(self):
        security = RecordingLiveSecurity()
        clipboard_tools = RecordingLiveClipboardTools()
        tool = self.make_tools(
            security=security,
            clipboard_tools=clipboard_tools,
        )["set_clipboard_text"]

        result = asyncio.run(tool("Bonjour"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "set_clipboard_text")
        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(security.intents[0].action, "set_clipboard_text")
        self.assertEqual(clipboard_tools.calls, [("set_text", "Bonjour")])

    def test_clipboard_tool_arguments_are_not_modified_by_log_redaction(self):
        secret = "JARVIS_CLIPBOARD_ARGUMENT_SENTINEL_41d4"
        clipboard_tools = RecordingLiveClipboardTools()
        tool = self.make_tools(clipboard_tools=clipboard_tools)[
            "set_clipboard_text"
        ]

        result = asyncio.run(tool(secret))

        self.assertTrue(result["ok"])
        self.assertEqual(clipboard_tools.calls, [("set_text", secret)])

    def test_get_clipboard_text_still_returns_text_to_gemini(self):
        secret = "JARVIS_CLIPBOARD_RESULT_SENTINEL_60bb"
        clipboard_tools = RecordingLiveClipboardTools(
            text_state={
                "has_text": True,
                "text": secret,
                "length": len(secret),
                "returned_length": len(secret),
                "truncated": False,
                "content_type": "text",
            },
        )
        tool = self.make_tools(clipboard_tools=clipboard_tools)[
            "get_clipboard_text"
        ]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], secret)

    def test_clear_clipboard_success_uses_security_and_backend(self):
        security = RecordingLiveSecurity()
        clipboard_tools = RecordingLiveClipboardTools()
        tool = self.make_tools(
            security=security,
            clipboard_tools=clipboard_tools,
        )["clear_clipboard"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "clear_clipboard")
        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(security.intents[0].action, "clear_clipboard")
        self.assertEqual(clipboard_tools.calls, [("clear",)])

    def test_clipboard_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(
            tools["get_clipboard_text"].info.name,
            "get_clipboard_text",
        )
        self.assertIn(
            "presse-papiers",
            tools["get_clipboard_text"].info.description.lower(),
        )
        self.assertEqual(
            tools["set_clipboard_text"].info.name,
            "set_clipboard_text",
        )
        self.assertEqual(
            tools["clear_clipboard"].info.name,
            "clear_clipboard",
        )

    def test_clipboard_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["get_clipboard_text"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_clipboard_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["set_clipboard_text"]
            result = asyncio.run(tool("Bonjour"))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("set_clipboard_text", ("Bonjour",))])

    def test_clipboard_tools_share_a_lock_without_affecting_media_lock(self):
        registry = ToolRegistry(
            clipboard_capability=object(),
            media_capability=object(),
        )

        self.assertIsNot(registry.clipboard_lock, registry.media_lock)
        self.assertTrue(hasattr(registry.clipboard_lock, "acquire"))

    def test_clipboard_debug_does_not_log_raw_secret_text(self):
        secret = "JARVIS_CLIPBOARD_SECRET_SENTINEL_7f31"
        clipboard_tools = RecordingLiveClipboardTools(
            text_state={
                "has_text": True,
                "text": secret,
                "length": len(secret),
                "returned_length": len(secret),
                "truncated": False,
                "content_type": "text",
            },
            set_state={
                "command_executed": True,
                "state_confirmed": True,
                "length": len(secret),
                "has_text": True,
                "content_type": "text",
            },
        )
        tools = self.make_tools(clipboard_tools=clipboard_tools)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["get_clipboard_text"]())
                asyncio.run(tools["set_clipboard_text"](secret))

        debug_output = output.getvalue()

        self.assertNotIn(secret, debug_output)
        self.assertIn("get_clipboard_text", debug_output)
        self.assertIn("set_clipboard_text", debug_output)
        self.assertIn(f"length: {len(secret)}", debug_output)

    def test_existing_capability_tools_remain_exposed_with_clipboard(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("play_pause", tools)
        self.assertIn("get_battery_status", tools)
        self.assertIn("get_active_window", tools)
        self.assertIn("list_files", tools)


class LiveKeyboardToolTest(unittest.TestCase):
    def make_tools(self, keyboard_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            keyboard_capability=(
                keyboard_capability or RecordingLiveKeyboardCapability()
            ),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_keyboard_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["type_text"].info.name, "type_text")
        self.assertEqual(tools["press_key"].info.name, "press_key")
        self.assertEqual(tools["hotkey"].info.name, "hotkey")
        self.assertIn("fenetre", tools["type_text"].info.description.lower())
        self.assertIn("raccourci", tools["hotkey"].info.description.lower())
        self.assertIn('["command", "a"]', tools["hotkey"].info.description)

    def test_type_text_success_returns_structured_result_without_confirmation(self):
        capability = RecordingLiveKeyboardCapability()
        tool = self.make_tools(keyboard_capability=capability)["type_text"]

        result = asyncio.run(tool("Bonjour"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "type_text")
        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(result["length"], 7)
        self.assertNotIn("text", result)
        self.assertEqual(capability.calls, [("type_text", "Bonjour")])

    def test_press_key_success_returns_structured_result(self):
        capability = RecordingLiveKeyboardCapability()
        tool = self.make_tools(keyboard_capability=capability)["press_key"]

        result = asyncio.run(tool("enter"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["key"], "enter")
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(capability.calls, [("press_key", "enter")])

    def test_hotkey_success_returns_structured_result(self):
        capability = RecordingLiveKeyboardCapability()
        tool = self.make_tools(keyboard_capability=capability)["hotkey"]

        result = asyncio.run(tool(["command", "a"]))

        self.assertTrue(result["ok"])
        self.assertEqual(result["keys"], ["command", "a"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(capability.calls, [("hotkey", ["command", "a"])])

    def test_keyboard_tools_return_awaitable_result_for_livekit(self):
        tool = self.make_tools()["press_key"]

        result = tool("enter")

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_keyboard_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["hotkey"]
            result = asyncio.run(tool(["command", "a"]))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("hotkey", (["command", "a"],))])

    def test_keyboard_tools_share_a_lock_without_affecting_existing_locks(self):
        registry = ToolRegistry(
            keyboard_capability=object(),
            media_capability=object(),
            clipboard_capability=object(),
        )

        self.assertIsNot(registry.keyboard_lock, registry.media_lock)
        self.assertIsNot(registry.keyboard_lock, registry.clipboard_lock)
        self.assertTrue(hasattr(registry.keyboard_lock, "acquire"))

    def test_keyboard_debug_does_not_log_raw_text(self):
        secret = "JARVIS_KEYBOARD_SECRET_SENTINEL_42a1"
        capability = RecordingLiveKeyboardCapability()
        tools = self.make_tools(keyboard_capability=capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["type_text"](secret))

        debug_output = output.getvalue()

        self.assertNotIn(secret, debug_output)
        self.assertIn("type_text", debug_output)
        self.assertIn(f"length: {len(secret)}", debug_output)

    def test_existing_capability_tools_remain_exposed_with_keyboard(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("get_active_window", tools)
        self.assertIn("get_clipboard_text", tools)
