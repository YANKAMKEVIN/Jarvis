import asyncio
import unittest
import unittest.mock

from jarvis.capabilities.results import ToolResult
from jarvis.live.registry import SAFE_MODE_ALLOWED, create_live_registry


class FakeMemory:
    def log_action(self, *a, **k):
        return None


class FakeAudio:
    """Records calls so a test can prove a blocked tool ran nothing."""

    def __init__(self):
        self.calls = []

    def set_volume(self, volume):
        self.calls.append(("set_volume", volume))
        return ToolResult.success("set_volume", "ok", volume=volume)

    def get_volume(self):
        self.calls.append(("get_volume",))
        return ToolResult.success("get_volume", "ok", volume=42)


class ReadOnlyModeTests(unittest.TestCase):
    def _registry(self):
        audio = FakeAudio()
        registry = create_live_registry(
            memory_capability=FakeMemory(), audio_capability=audio,
        )
        tools = {t.info.name: t for t in registry.livekit_tools()}
        return registry, tools, audio

    def test_every_tool_call_is_journaled_by_name_only(self):
        _, tools, _ = self._registry()
        with unittest.mock.patch("jarvis.live.registry.log_event") as logged:
            asyncio.run(tools["get_volume"]())   # allowed in safe mode
            asyncio.run(tools["set_volume"](80))  # guarded
        self.assertEqual([c.args for c in logged.call_args_list],
                         [("tool", "get_volume"), ("tool", "set_volume")])

    def test_defaults_off(self):
        registry, _, _ = self._registry()
        self.assertFalse(registry.read_only_mode)

    def test_blocked_tool_refuses_and_runs_nothing_in_safe_mode(self):
        registry, tools, audio = self._registry()
        registry.read_only_mode = True
        result = asyncio.run(tools["set_volume"](80))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "read_only_mode")
        # The capability was never touched: nothing was changed.
        self.assertEqual(audio.calls, [])

    def test_allowed_read_still_works_in_safe_mode(self):
        registry, tools, audio = self._registry()
        registry.read_only_mode = True
        result = asyncio.run(tools["get_volume"]())
        self.assertTrue(result["ok"])
        self.assertEqual(result["volume"], 42)
        self.assertEqual(audio.calls, [("get_volume",)])

    def test_blocked_tool_runs_again_once_safe_mode_is_off(self):
        registry, tools, audio = self._registry()
        registry.read_only_mode = True
        asyncio.run(tools["set_volume"](80))
        registry.read_only_mode = False
        result = asyncio.run(tools["set_volume"](80))
        self.assertTrue(result["ok"])
        self.assertEqual(audio.calls, [("set_volume", 80)])

    def test_enable_and_disable_toggle_the_flag(self):
        registry, tools, _ = self._registry()
        enabled = asyncio.run(tools["enable_safe_mode"]())
        self.assertTrue(enabled["ok"])
        self.assertTrue(enabled["read_only_mode"])
        self.assertTrue(registry.read_only_mode)

        disabled = asyncio.run(tools["disable_safe_mode"]())
        self.assertTrue(disabled["ok"])
        self.assertFalse(disabled["read_only_mode"])
        self.assertFalse(registry.read_only_mode)

    def test_switch_is_never_blocked_by_safe_mode(self):
        # The way out must always work, even from inside safe mode.
        registry, tools, _ = self._registry()
        registry.read_only_mode = True
        result = asyncio.run(tools["disable_safe_mode"]())
        self.assertTrue(result["ok"])
        self.assertFalse(registry.read_only_mode)

    def test_planner_tools_share_the_same_guard(self):
        # A mission must not do outward actions in safe mode either.
        registry, _, _ = self._registry()
        registry.read_only_mode = True
        planner = {t.info.name: t for t in registry.planner_tools}
        result = asyncio.run(planner["set_volume"](80))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "read_only_mode")

    def test_outward_and_mutating_tools_are_not_allowlisted(self):
        # Default-deny: the dangerous ones must be blocked (absent from the set).
        for name in (
            "open_app", "close_app", "set_volume", "set_brightness",
            "lock_screen", "run_shortcut", "draft_email",
            "create_calendar_event", "move_file", "rename_file",
            "create_folder", "set_clipboard_text", "type_text", "press_key",
            "hotkey", "click", "prepare_send_message", "send_last_web_result",
            "schedule_message", "confirm_action", "clear_personal_data",
            "browse_open_url", "run_macro", "run_procedure",
            "run_claude_task", "open_claude_session",
        ):
            self.assertNotIn(name, SAFE_MODE_ALLOWED, name)

    def test_reads_and_own_stores_are_allowlisted(self):
        for name in (
            "get_volume", "self_check", "list_files", "ask_about_document",
            "list_calendar_events", "list_unread_emails", "find_free_slots",
            "search_notes", "read_note", "recall", "search_the_web",
            "save_note", "append_note", "manage_checklist", "remember",
            "set_reminder", "task_status", "cancel_task", "recent_activity",
        ):
            self.assertIn(name, SAFE_MODE_ALLOWED, name)


if __name__ == "__main__":
    unittest.main()
