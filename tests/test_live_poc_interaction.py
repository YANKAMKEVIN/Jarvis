"""Live POC: composite interaction tools."""
import asyncio
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis.capabilities.results import ToolResult
from jarvis.live.tools import ToolRegistry, create_live_tools
from live_poc_fakes_core import RecordingLiveSecurity
from live_poc_fakes_ui import RecordingLiveInteractionCapability


class LiveInteractionToolTest(unittest.TestCase):
    def make_tools(self, interaction_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            interaction_capability=(
                interaction_capability
                or RecordingLiveInteractionCapability()
            ),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_interaction_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(
            tools["select_all_and_copy"].info.name,
            "select_all_and_copy",
        )
        self.assertEqual(
            tools["focus_app_ui_and_type"].info.name,
            "focus_app_ui_and_type",
        )
        self.assertEqual(
            tools["open_app_and_focus_ui"].info.name,
            "open_app_and_focus_ui",
        )
        self.assertIn("command+a", tools["select_all_and_copy"].info.description)
        self.assertIn("saisit du texte", tools["focus_app_ui_and_type"].info.description)
        description = tools["focus_app_ui_and_type"].info.description
        self.assertIn("obligatoirement query", description)
        self.assertIn("query=None", description)
        self.assertIn("editable_target_not_verified", description)
        self.assertIn("aucune saisie ni Enter", description)
        self.assertIn("sans taper", tools["open_app_and_focus_ui"].info.description)

    def test_select_all_and_copy_success_returns_structured_steps(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["select_all_and_copy"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "select_all_and_copy")
        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(capability.calls, [("select_all_and_copy",)])

    def test_select_all_and_delete_is_named_and_distinct_from_copy(self):
        tools = self.make_tools()

        self.assertEqual(
            tools["select_all_and_delete"].info.name,
            "select_all_and_delete",
        )
        description = tools["select_all_and_delete"].info.description
        self.assertIn("supprime", description)
        self.assertIn("jamais select_all_and_copy", description)
        self.assertNotIn("supprime", tools["select_all_and_copy"].info.description)

    def test_select_all_and_delete_routes_to_capability(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["select_all_and_delete"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "select_all_and_delete")
        self.assertFalse(result["state_confirmed"])
        self.assertTrue(result["deletion_executed"])
        self.assertEqual(capability.calls, [("select_all_and_delete",)])

    def test_send_prompt_to_app_submits_via_focus_app_ui_and_type(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["send_prompt_to_app"]

        # A non-direct-type app uses the AX-verified flow with press_enter=True.
        result = asyncio.run(tool("Notes", "Explique la relativite"))

        self.assertTrue(result["ok"])
        self.assertEqual(
            capability.calls,
            [("focus_app_ui_and_type", "Notes", "Explique la relativite", None, None, True)],
        )

    def test_send_prompt_to_app_claude_types_directly(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["send_prompt_to_app"]

        result = asyncio.run(tool("Claude", "Explique la relativite"))

        self.assertTrue(result["ok"])
        # Electron app → direct type, no AX field verification.
        self.assertEqual(
            capability.calls,
            [("open_app_and_type", "Claude", "Explique la relativite", True)],
        )

    def test_send_prompt_to_app_other_app_uses_ax_verified_path(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["send_prompt_to_app"]

        result = asyncio.run(tool("TextEdit", "Bonjour"))

        self.assertTrue(result["ok"])
        self.assertEqual(capability.calls[0][0], "focus_app_ui_and_type")

    def test_send_prompt_to_app_explicit_query_overrides_direct_type(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["send_prompt_to_app"]

        result = asyncio.run(tool("Claude", "Salut", "un champ"))

        self.assertTrue(result["ok"])
        # Explicit query → AX-verified path even for a direct-type app.
        self.assertEqual(capability.calls[0][0], "focus_app_ui_and_type")

    def test_send_prompt_to_app_description_mentions_claude_and_submit(self):
        tools = self.make_tools()
        description = tools["send_prompt_to_app"].info.description
        self.assertIn("Claude", description)
        self.assertIn("Entree", description)

    def test_interaction_debug_never_logs_arbitrary_data_fields(self):
        class LeakyInteraction:
            def select_all_and_copy(self):
                return ToolResult.success(
                    action="select_all_and_copy",
                    message="ok",
                    command_executed=True,
                    state_confirmed=False,
                    text="CLIPBOARD_SECRET_CONTENT",
                    steps=[{"name": "get_clipboard_text_after", "ok": True}],
                )

        tools = self.make_tools(interaction_capability=LeakyInteraction())

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["select_all_and_copy"]())

        self.assertNotIn("CLIPBOARD_SECRET_CONTENT", output.getvalue())

    def test_focus_app_ui_and_type_uses_text_but_debug_uses_length(self):
        secret_text = "JARVIS_INTERACTION_SECRET_TEXT"
        secret_query = "JARVIS_INTERACTION_SECRET_QUERY"
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(interaction_capability=capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                result = asyncio.run(
                    tools["focus_app_ui_and_type"](
                        "Safari",
                        secret_text,
                        secret_query,
                        "AXTextField",
                        True,
                    )
                )

        debug_output = output.getvalue()

        self.assertTrue(result["ok"])
        self.assertEqual(result["text_length"], len(secret_text))
        self.assertEqual(result["query_length"], len(secret_query))
        self.assertEqual(
            capability.calls,
            [(
                "focus_app_ui_and_type",
                "Safari",
                secret_text,
                secret_query,
                "AXTextField",
                True,
            )],
        )
        self.assertNotIn(secret_text, debug_output)
        self.assertNotIn(secret_query, debug_output)
        self.assertIn(f"text_length: {len(secret_text)}", debug_output)
        self.assertIn(f"query_length: {len(secret_query)}", debug_output)

    def test_open_app_and_focus_ui_returns_confirmed_state(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["open_app_and_focus_ui"]

        result = asyncio.run(tool("Safari", "barre de recherche", "AXTextField"))

        self.assertTrue(result["ok"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(result["query_length"], len("barre de recherche"))
        self.assertEqual(
            capability.calls,
            [("open_app_and_focus_ui", "Safari", "barre de recherche", "AXTextField")],
        )

    def test_live_tools_use_to_thread_for_interaction_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["select_all_and_copy"]
            result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("select_all_and_copy", ())])

    def test_interaction_tools_share_a_lock_without_affecting_existing_locks(self):
        registry = ToolRegistry(
            interaction_capability=object(),
            ui_accessibility_capability=object(),
            mouse_capability=object(),
            keyboard_capability=object(),
            media_capability=object(),
            clipboard_capability=object(),
        )

        self.assertIsNot(registry.interaction_lock, registry.ui_lock)
        self.assertIsNot(registry.interaction_lock, registry.mouse_lock)
        self.assertIsNot(registry.interaction_lock, registry.keyboard_lock)
        self.assertIsNot(registry.interaction_lock, registry.clipboard_lock)
        self.assertTrue(hasattr(registry.interaction_lock, "acquire"))
