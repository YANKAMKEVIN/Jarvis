"""Live POC: mouse and UI accessibility tools."""
import asyncio
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis.live.tools import ToolRegistry, create_live_tools
from live_poc_fakes_core import RecordingLiveSecurity
from live_poc_fakes_input import RecordingLiveMouseCapability
from live_poc_fakes_ui import RecordingLiveUIAccessibilityCapability


class LiveMouseToolTest(unittest.TestCase):
    def make_tools(self, mouse_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            mouse_capability=(
                mouse_capability or RecordingLiveMouseCapability()
            ),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_mouse_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["get_mouse_position"].info.name, "get_mouse_position")
        self.assertEqual(tools["move_mouse"].info.name, "move_mouse")
        self.assertEqual(tools["click"].info.name, "click")
        self.assertEqual(tools["double_click"].info.name, "double_click")
        self.assertEqual(tools["right_click"].info.name, "right_click")
        self.assertEqual(tools["scroll"].info.name, "scroll")
        self.assertIn("coordonnees", tools["move_mouse"].info.description.lower())
        self.assertIn("up", tools["scroll"].info.description)
        self.assertIn("down", tools["scroll"].info.description)

    def test_get_mouse_position_success_returns_structured_result(self):
        capability = RecordingLiveMouseCapability()
        tool = self.make_tools(mouse_capability=capability)["get_mouse_position"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "get_mouse_position")
        self.assertEqual(result["x"], 10)
        self.assertEqual(result["y"], 20)
        self.assertEqual(result["screen_index"], 0)
        self.assertEqual(capability.calls, [("get_mouse_position",)])

    def test_move_mouse_success_returns_structured_result(self):
        capability = RecordingLiveMouseCapability()
        tool = self.make_tools(mouse_capability=capability)["move_mouse"]

        result = asyncio.run(tool(100, 200))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "move_mouse")
        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(result["target_x"], 100)
        self.assertEqual(result["target_y"], 200)
        self.assertEqual(capability.calls, [("move_mouse", 100, 200)])

    def test_click_tools_return_unconfirmed_results(self):
        capability = RecordingLiveMouseCapability()
        tools = self.make_tools(mouse_capability=capability)

        click = asyncio.run(tools["click"]())
        double_click = asyncio.run(tools["double_click"]())
        right_click = asyncio.run(tools["right_click"]())

        self.assertFalse(click["state_confirmed"])
        self.assertEqual(click["button"], "left")
        self.assertEqual(click["click_count"], 1)
        self.assertEqual(double_click["click_count"], 2)
        self.assertEqual(right_click["button"], "right")
        self.assertEqual(
            capability.calls,
            [("click",), ("double_click",), ("right_click",)],
        )

    def test_scroll_success_returns_structured_result(self):
        capability = RecordingLiveMouseCapability()
        tool = self.make_tools(mouse_capability=capability)["scroll"]

        result = asyncio.run(tool("down", 4))

        self.assertTrue(result["ok"])
        self.assertEqual(result["direction"], "down")
        self.assertEqual(result["amount"], 4)
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(capability.calls, [("scroll", "down", 4)])

    def test_mouse_tools_return_awaitable_result_for_livekit(self):
        tool = self.make_tools()["get_mouse_position"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_mouse_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["move_mouse"]
            result = asyncio.run(tool(100, 200))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("move_mouse", (100, 200))])

    def test_mouse_tools_share_a_lock_without_affecting_existing_locks(self):
        registry = ToolRegistry(
            mouse_capability=object(),
            keyboard_capability=object(),
            media_capability=object(),
            clipboard_capability=object(),
        )

        self.assertIsNot(registry.mouse_lock, registry.keyboard_lock)
        self.assertIsNot(registry.mouse_lock, registry.media_lock)
        self.assertIsNot(registry.mouse_lock, registry.clipboard_lock)
        self.assertTrue(hasattr(registry.mouse_lock, "acquire"))

    def test_mouse_debug_logs_only_metadata(self):
        capability = RecordingLiveMouseCapability()
        tools = self.make_tools(mouse_capability=capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["scroll"]("down", 4))

        debug_output = output.getvalue()

        self.assertIn("scroll", debug_output)
        self.assertIn("direction: down", debug_output)
        self.assertIn("amount: 4", debug_output)
        self.assertIn("state_confirmed: False", debug_output)

    def test_existing_capability_tools_remain_exposed_with_mouse(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("get_active_window", tools)
        self.assertIn("type_text", tools)


class LiveUIAccessibilityToolTest(unittest.TestCase):
    def make_tools(self, ui_accessibility_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            ui_accessibility_capability=(
                ui_accessibility_capability
                or RecordingLiveUIAccessibilityCapability()
            ),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_ui_accessibility_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["inspect_ui"].info.name, "inspect_ui")
        self.assertEqual(tools["find_ui_elements"].info.name, "find_ui_elements")
        self.assertEqual(tools["focus_ui_element"].info.name, "focus_ui_element")
        self.assertEqual(tools["activate_ui_element"].info.name, "activate_ui_element")
        self.assertIn("Accessibility", tools["inspect_ui"].info.description)
        self.assertIn("AXPress", tools["activate_ui_element"].info.description)

    def test_inspect_ui_success_returns_structured_result(self):
        capability = RecordingLiveUIAccessibilityCapability()
        tool = self.make_tools(ui_accessibility_capability=capability)["inspect_ui"]

        result = asyncio.run(tool(3, 20))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "inspect_ui")
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["truncated"])
        self.assertEqual(capability.calls, [("inspect_ui", 3, 20)])

    def test_find_ui_elements_uses_query_but_debug_uses_length(self):
        capability = RecordingLiveUIAccessibilityCapability()
        tool = self.make_tools(ui_accessibility_capability=capability)["find_ui_elements"]

        result = asyncio.run(tool("Secret label", "AXButton"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["query_length"], len("Secret label"))
        self.assertEqual(
            capability.calls,
            [("find_ui_elements", "Secret label", "AXButton")],
        )

    def test_focus_and_activate_return_command_state(self):
        capability = RecordingLiveUIAccessibilityCapability()
        tools = self.make_tools(ui_accessibility_capability=capability)

        focus = asyncio.run(tools["focus_ui_element"]("Recherche", "AXTextField"))
        activate = asyncio.run(tools["activate_ui_element"]("Continuer", "AXButton"))

        self.assertTrue(focus["state_confirmed"])
        self.assertTrue(activate["command_executed"])
        self.assertFalse(activate["state_confirmed"])
        self.assertEqual(
            capability.calls,
            [
                ("focus_ui_element", "Recherche", "AXTextField"),
                ("activate_ui_element", "Continuer", "AXButton"),
            ],
        )

    def test_ui_accessibility_tools_return_awaitable_result_for_livekit(self):
        tool = self.make_tools()["inspect_ui"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_ui_accessibility_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["activate_ui_element"]
            result = asyncio.run(tool("Continuer", "AXButton"))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("activate_ui_element", ("Continuer", "AXButton"))])

    def test_ui_tools_share_a_lock_without_affecting_existing_locks(self):
        registry = ToolRegistry(
            ui_accessibility_capability=object(),
            mouse_capability=object(),
            keyboard_capability=object(),
            media_capability=object(),
            clipboard_capability=object(),
        )

        self.assertIsNot(registry.ui_lock, registry.mouse_lock)
        self.assertIsNot(registry.ui_lock, registry.keyboard_lock)
        self.assertIsNot(registry.ui_lock, registry.media_lock)
        self.assertIsNot(registry.ui_lock, registry.clipboard_lock)
        self.assertTrue(hasattr(registry.ui_lock, "acquire"))

    def test_ui_debug_does_not_log_raw_query_or_labels(self):
        secret = "JARVIS_UI_SECRET_LABEL_8d13"
        capability = RecordingLiveUIAccessibilityCapability()
        tools = self.make_tools(ui_accessibility_capability=capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["find_ui_elements"](secret, "AXButton"))

        debug_output = output.getvalue()

        self.assertNotIn(secret, debug_output)
        self.assertIn("find_ui_elements", debug_output)
        self.assertIn(f"query_length: {len(secret)}", debug_output)

    def test_existing_capability_tools_remain_exposed_with_ui_accessibility(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("get_active_window", tools)
        self.assertIn("type_text", tools)
        self.assertIn("click", tools)
