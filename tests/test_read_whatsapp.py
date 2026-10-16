import asyncio
import os
import unittest
from unittest.mock import patch

from jarvis.capabilities.results import ToolResult
from jarvis.live.registry import create_live_registry


class FakeVision:
    def __init__(self):
        self.calls = []

    def ask_about_screen(self, question, target, app_name):
        self.calls.append((question, target, app_name))
        return ToolResult.success(
            action="ask_about_screen",
            message="Conversation avec Marie : elle propose de dejeuner demain.",
            target=target, app=app_name,
        )


class FakeWindows:
    def __init__(self):
        self.calls = []

    def focus_window(self, app_name):
        self.calls.append(("focus_window", app_name))
        return ToolResult.success(
            action="focus_window", message="ok", state_confirmed=True, target_app=app_name,
        )


class FakeMemory:
    def log_action(self, *a, **k):
        return None


class ReadWhatsAppTests(unittest.TestCase):
    def _tools(self, vision, windows):
        registry = create_live_registry(
            vision_capability=vision,
            window_capability=windows,
            memory_capability=FakeMemory(),
        )
        return {t.info.name: t for t in registry.livekit_tools()}

    def test_reads_via_vision_when_enabled(self):
        vision, windows = FakeVision(), FakeWindows()
        with patch.dict(os.environ, {"JARVIS_VISION_ENABLED": "1"}, clear=False):
            tools = self._tools(vision, windows)
            result = asyncio.run(tools["read_whatsapp_conversation"]())

        self.assertTrue(result["ok"])
        self.assertIn("Marie", result["message"])
        self.assertIn(("focus_window", "WhatsApp"), windows.calls)  # brought frontmost
        self.assertEqual(vision.calls[0][1], "window")
        self.assertEqual(vision.calls[0][2], "WhatsApp")

    def test_custom_question_is_passed(self):
        vision, windows = FakeVision(), FakeWindows()
        with patch.dict(os.environ, {"JARVIS_VISION_ENABLED": "1"}, clear=False):
            tools = self._tools(vision, windows)
            asyncio.run(tools["read_whatsapp_conversation"]("Qui a ecrit en dernier ?"))
        self.assertEqual(vision.calls[0][0], "Qui a ecrit en dernier ?")

    def test_blocked_when_vision_disabled(self):
        vision, windows = FakeVision(), FakeWindows()
        with patch.dict(os.environ, {"JARVIS_VISION_ENABLED": "0"}, clear=False):
            tools = self._tools(vision, windows)
            result = asyncio.run(tools["read_whatsapp_conversation"]())
        self.assertFalse(result["ok"])
        self.assertEqual(vision.calls, [])  # vision not invoked when disabled


if __name__ == "__main__":
    unittest.main()
