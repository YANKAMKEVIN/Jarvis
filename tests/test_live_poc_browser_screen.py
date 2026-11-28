"""Live POC: browser, screenshot and vision tools."""
import asyncio
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis.live.tools import ToolRegistry, create_live_tools
from live_poc_fakes_core import RecordingLiveSecurity
from live_poc_fakes_ui import (
    RecordingLiveBrowserCapability,
    RecordingLiveScreenshotCapability,
    RecordingLiveVisionCapability,
)


class LiveBrowserToolTest(unittest.TestCase):
    def make_tools(self, browser_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            browser_capability=browser_capability or RecordingLiveBrowserCapability(),
        )
        return {tool.info.name: tool for tool in tools}

    def test_browser_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        for name in (
            "browse_open_url",
            "browse_search_web",
            "browse_get_active_tab",
            "browse_list_tabs",
            "browse_activate_tab",
        ):
            self.assertEqual(tools[name].info.name, name)

        self.assertIn("state_confirmed", tools["browse_open_url"].info.description)
        self.assertIn("ambiguous_tab", tools["browse_activate_tab"].info.description)

    def test_browse_open_url_routes_to_capability(self):
        capability = RecordingLiveBrowserCapability()
        tool = self.make_tools(capability)["browse_open_url"]

        result = asyncio.run(tool("youtube.com", "Safari", True))

        self.assertTrue(result["ok"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(
            capability.calls,
            [("open_url", "youtube.com", "Safari", True)],
        )

    def test_browse_search_web_routes_to_capability(self):
        capability = RecordingLiveBrowserCapability()
        tool = self.make_tools(capability)["browse_search_web"]

        result = asyncio.run(tool("meteo paris", None, "duckduckgo"))

        self.assertTrue(result["ok"])
        self.assertEqual(
            capability.calls,
            [("search_web", "meteo paris", None, "duckduckgo")],
        )

    def test_browse_activate_tab_routes_query_to_capability(self):
        capability = RecordingLiveBrowserCapability()
        tool = self.make_tools(capability)["browse_activate_tab"]

        result = asyncio.run(tool("github"))

        self.assertTrue(result["ok"])
        self.assertEqual(capability.calls, [("activate_tab", "github", None, None)])

    def test_browse_activate_tab_routes_explicit_index_to_capability(self):
        capability = RecordingLiveBrowserCapability()
        tool = self.make_tools(capability)["browse_activate_tab"]

        result = asyncio.run(tool(None, 8))

        self.assertTrue(result["ok"])
        self.assertEqual(result["active_index"], 8)
        self.assertEqual(capability.calls, [("activate_tab", None, 8, None)])

    def test_browser_debug_logs_host_not_full_url_or_query(self):
        capability = RecordingLiveBrowserCapability()
        tools = self.make_tools(capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["browse_search_web"]("SECRET_QUERY_TEXT", None, None))

        debug_output = output.getvalue()

        self.assertNotIn("SECRET_QUERY_TEXT", debug_output)
        self.assertNotIn("https://www.google.com/search", debug_output)
        self.assertIn("active_host", debug_output)

    def test_browser_has_its_own_lock(self):
        registry = ToolRegistry(
            browser_capability=object(),
            interaction_capability=object(),
        )

        self.assertIsNot(registry.browser_lock, registry.interaction_lock)
        self.assertTrue(hasattr(registry.browser_lock, "acquire"))


class LiveScreenshotToolTest(unittest.TestCase):
    def make_tools(self, screenshot_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            screenshot_capability=(
                screenshot_capability or RecordingLiveScreenshotCapability()
            ),
        )
        return {tool.info.name: tool for tool in tools}

    def test_screenshot_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        for name in ("capture_screen", "capture_region", "capture_window"):
            self.assertEqual(tools[name].info.name, name)

        self.assertIn("ne contient pas l'image", tools["capture_screen"].info.description)
        self.assertIn("coordonnees", tools["capture_region"].info.description)

    def test_capture_screen_routes_to_capability(self):
        capability = RecordingLiveScreenshotCapability()
        tool = self.make_tools(capability)["capture_screen"]

        result = asyncio.run(tool(None, 1))

        self.assertTrue(result["ok"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(capability.calls, [("capture_screen", None, 1)])

    def test_capture_region_routes_to_capability(self):
        capability = RecordingLiveScreenshotCapability()
        tool = self.make_tools(capability)["capture_region"]

        result = asyncio.run(tool(10, 20, 30, 40, None))

        self.assertTrue(result["ok"])
        self.assertEqual(
            capability.calls,
            [("capture_region", 10, 20, 30, 40, None)],
        )

    def test_capture_window_routes_to_capability(self):
        capability = RecordingLiveScreenshotCapability()
        tool = self.make_tools(capability)["capture_window"]

        result = asyncio.run(tool("Notes", None))

        self.assertTrue(result["ok"])
        self.assertEqual(capability.calls, [("capture_window", "Notes", None)])

    def test_screenshot_debug_logs_basename_not_full_path(self):
        capability = RecordingLiveScreenshotCapability()
        tools = self.make_tools(capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["capture_screen"](None, None))

        debug_output = output.getvalue()

        self.assertNotIn("/Users/someone/Pictures/Jarvis", debug_output)
        self.assertIn("jarvis-screenshot-x.png", debug_output)

    def test_screenshot_has_its_own_lock(self):
        registry = ToolRegistry(
            screenshot_capability=object(),
            browser_capability=object(),
        )

        self.assertIsNot(registry.screenshot_lock, registry.browser_lock)
        self.assertTrue(hasattr(registry.screenshot_lock, "acquire"))


class LiveVisionToolTest(unittest.TestCase):
    def make_tools(self, vision_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            vision_capability=vision_capability or RecordingLiveVisionCapability(),
        )
        return {tool.info.name: tool for tool in tools}

    def test_vision_tools_are_named_and_read_only(self):
        tools = self.make_tools()

        self.assertEqual(tools["describe_screen"].info.name, "describe_screen")
        self.assertEqual(tools["ask_about_screen"].info.name, "ask_about_screen")
        for name in ("describe_screen", "ask_about_screen"):
            description = tools[name].info.description
            self.assertIn("Accessibility", description)
            self.assertIn("coordonnee", description)

    def test_describe_screen_routes_when_enabled(self):
        capability = RecordingLiveVisionCapability()
        tool = self.make_tools(capability)["describe_screen"]

        with patch.dict(os.environ, {"JARVIS_VISION_ENABLED": "1"}, clear=True):
            result = asyncio.run(tool("screen", None))

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "screen")
        self.assertEqual(capability.calls, [("describe_screen", "screen", None)])

    def test_ask_about_screen_routes_when_enabled(self):
        capability = RecordingLiveVisionCapability()
        tool = self.make_tools(capability)["ask_about_screen"]

        with patch.dict(os.environ, {"JARVIS_VISION_ENABLED": "1"}, clear=True):
            result = asyncio.run(tool("Quelle temperature ?", "window", None))

        self.assertTrue(result["ok"])
        self.assertEqual(
            capability.calls,
            [("ask_about_screen", "Quelle temperature ?", "window", None)],
        )

    def test_vision_disabled_blocks_without_capturing(self):
        capability = RecordingLiveVisionCapability()
        tool = self.make_tools(capability)["describe_screen"]

        with patch.dict(os.environ, {}, clear=True):  # JARVIS_VISION_ENABLED unset
            result = asyncio.run(tool("window", None))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "vision_disabled")
        self.assertEqual(capability.calls, [])  # capability never invoked

    def test_vision_debug_logs_metadata_not_analysis_or_question(self):
        capability = RecordingLiveVisionCapability(analysis="SECRET_ANALYSIS_TEXT")
        tools = self.make_tools(capability)

        with patch.dict(
            os.environ,
            {"JARVIS_VISION_ENABLED": "1", "JARVIS_DEBUG_LIVE": "1"},
            clear=True,
        ):
            output = StringIO()
            with redirect_stdout(output):
                asyncio.run(tools["ask_about_screen"]("SECRET_QUESTION_TEXT", "window", None))

        debug_output = output.getvalue()

        self.assertNotIn("SECRET_ANALYSIS_TEXT", debug_output)
        self.assertNotIn("SECRET_QUESTION_TEXT", debug_output)
        self.assertNotIn("/Users/someone/Pictures/Jarvis", debug_output)
        self.assertIn("shot.png", debug_output)
        self.assertIn("gemini-2.5-flash", debug_output)

    def test_vision_has_its_own_lock(self):
        registry = ToolRegistry(
            vision_capability=object(),
            screenshot_capability=object(),
        )

        self.assertIsNot(registry.vision_lock, registry.screenshot_lock)
        self.assertTrue(hasattr(registry.vision_lock, "acquire"))
