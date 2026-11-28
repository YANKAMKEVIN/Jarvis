"""Live POC: prepared actions and their confirmation."""
import asyncio
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis.live.tools import ToolRegistry, create_live_registry
from live_poc_fakes_core import RecordingLiveSecurity
from live_poc_fakes_ui import (
    RecordingLiveInteractionCapability,
    RecordingLiveMessagingCapability,
)


class LiveConfirmationToolTest(unittest.TestCase):
    def make_tools(self, interaction_capability=None, messaging_capability=None):
        self.registry = create_live_registry(
            security=RecordingLiveSecurity(),
            interaction_capability=(
                interaction_capability or RecordingLiveInteractionCapability()
            ),
            messaging_capability=(
                messaging_capability or RecordingLiveMessagingCapability()
            ),
        )
        return {tool.info.name: tool for tool in self.registry.livekit_tools()}

    def test_confirmation_tools_are_named(self):
        tools = self.make_tools()

        for name in ("prepare_send_message", "confirm_action", "cancel_action"):
            self.assertEqual(tools[name].info.name, name)

        self.assertIn("token", tools["confirm_action"].info.description)
        self.assertIn("SANS l'envoyer", tools["prepare_send_message"].info.description)

    def test_prepare_does_not_send(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        result = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))

        self.assertTrue(result["ok"])
        self.assertTrue(result["requires_confirmation"])
        self.assertIn("token", result)
        self.assertEqual(result["target_app"], "WhatsApp")
        self.assertEqual(capability.calls, [])  # nothing sent yet

    def test_confirm_executes_the_prepared_send(self):
        interaction = RecordingLiveInteractionCapability()
        messaging = RecordingLiveMessagingCapability()
        tools = self.make_tools(interaction, messaging)

        prepared = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut", None))
        self.registry.note_user_turn()  # the user says "oui"
        result = asyncio.run(tools["confirm_action"](prepared["token"]))

        self.assertTrue(result["ok"])
        # WhatsApp supports the verified composer-send path (write + read back +
        # press send), which the WhatsApp composer needs since it never confirms
        # programmatic focus. The focus + type path is not used.
        self.assertEqual(messaging.calls[-1], ("send_text", "WhatsApp", "Salut"))
        self.assertEqual(interaction.calls, [])

    def test_explicit_query_overrides_composer_default(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        prepared = asyncio.run(
            tools["prepare_send_message"]("WhatsApp", "Salut", None, "Champ custom")
        )
        self.registry.note_user_turn()
        asyncio.run(tools["confirm_action"](prepared["token"]))

        self.assertEqual(capability.calls[0][3], "Champ custom")

    def test_confirm_is_single_use(self):
        messaging = RecordingLiveMessagingCapability()
        tools = self.make_tools(messaging_capability=messaging)

        prepared = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))
        token = prepared["token"]
        self.registry.note_user_turn()
        asyncio.run(tools["confirm_action"](token))
        self.registry.note_user_turn()
        second = asyncio.run(tools["confirm_action"](token))

        self.assertFalse(second["ok"])
        self.assertEqual(second["error_code"], "no_pending_action")
        sends = [call for call in messaging.calls if call[0] == "send_text"]
        self.assertEqual(len(sends), 1)  # executed only once

    def test_confirm_without_a_user_turn_sends_nothing_and_keeps_the_token(self):
        messaging = RecordingLiveMessagingCapability()
        tools = self.make_tools(messaging_capability=messaging)

        prepared = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))
        # The model calls confirm_action on its own (e.g. a prompt injection).
        early = asyncio.run(tools["confirm_action"](prepared["token"]))

        self.assertFalse(early["ok"])
        self.assertEqual(early["error_code"], "confirmation_needs_user_turn")
        self.assertNotIn(("send_text", "WhatsApp", "Salut"), messaging.calls)

        self.registry.note_user_turn()
        confirmed = asyncio.run(tools["confirm_action"](prepared["token"]))

        self.assertTrue(confirmed["ok"])
        self.assertEqual(messaging.calls[-1], ("send_text", "WhatsApp", "Salut"))

    def test_user_turn_before_preparation_does_not_confirm(self):
        messaging = RecordingLiveMessagingCapability()
        tools = self.make_tools(messaging_capability=messaging)

        self.registry.note_user_turn()  # "envoie Salut a Paul"
        prepared = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))
        result = asyncio.run(tools["confirm_action"](prepared["token"]))

        self.assertEqual(result["error_code"], "confirmation_needs_user_turn")
        self.assertNotIn(("send_text", "WhatsApp", "Salut"), messaging.calls)

    def test_confirm_unknown_token_sends_nothing(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        result = asyncio.run(tools["confirm_action"]("not-a-real-token"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "no_pending_action")
        self.assertEqual(capability.calls, [])

    def test_cancel_prevents_send(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        prepared = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))
        token = prepared["token"]
        cancelled = asyncio.run(tools["cancel_action"](token))
        confirmed = asyncio.run(tools["confirm_action"](token))

        self.assertTrue(cancelled["ok"])
        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(confirmed["error_code"], "no_pending_action")
        self.assertEqual(capability.calls, [])  # never sent

    def test_telegram_prepare_requires_a_recipient(self):
        messaging = RecordingLiveMessagingCapability()
        tools = self.make_tools(messaging_capability=messaging)

        result = asyncio.run(tools["prepare_send_message"]("Telegram", "Salut"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_recipient")
        self.assertNotIn("token", result)
        self.assertEqual(messaging.calls, [])

    def test_telegram_send_goes_through_the_verified_api_path(self):
        messaging = RecordingLiveMessagingCapability()
        interaction = RecordingLiveInteractionCapability()
        tools = self.make_tools(interaction, messaging)

        prepared = asyncio.run(
            tools["prepare_send_message"]("Telegram", "Salut", "Joel", "Champ custom")
        )
        self.registry.note_user_turn()
        confirmed = asyncio.run(tools["confirm_action"](prepared["token"]))

        self.assertTrue(confirmed["ok"])
        self.assertEqual(messaging.calls[0], ("ensure_recipient", "Telegram", "Joel"))
        self.assertEqual(messaging.calls[-1], ("send_text", "Telegram", "Salut"))
        # The recipient is passed to the send so it is re-resolved then, and an
        # explicit query never sends Telegram down the blind typing path.
        self.assertEqual(messaging.last_send_recipient, "Joel")
        self.assertEqual(interaction.calls, [])

    def test_telegram_unverified_recipient_prepares_nothing(self):
        messaging = RecordingLiveMessagingCapability(verified=False)
        tools = self.make_tools(messaging_capability=messaging)

        result = asyncio.run(tools["prepare_send_message"]("Telegram", "Salut", "Alice"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "recipient_not_verified")
        self.assertNotIn("token", result)

    def test_prepare_rejects_empty_message(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        result = asyncio.run(tools["prepare_send_message"]("WhatsApp", "   "))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_text")
        self.assertNotIn("token", result)

    def test_confirmation_debug_never_logs_message_text(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()
            with redirect_stdout(output):
                prepared = asyncio.run(
                    tools["prepare_send_message"]("WhatsApp", "SECRET_MSG_TEXT")
                )
                self.registry.note_user_turn()
                asyncio.run(tools["confirm_action"](prepared["token"]))

        debug_output = output.getvalue()
        self.assertNotIn("SECRET_MSG_TEXT", debug_output)
        self.assertIn("text_length: 15", debug_output)

    def test_prepare_with_verified_recipient_prepares_without_sending(self):
        interaction = RecordingLiveInteractionCapability()
        messaging = RecordingLiveMessagingCapability(verified=True)
        tools = self.make_tools(interaction, messaging)

        result = asyncio.run(
            tools["prepare_send_message"]("WhatsApp", "Salut", "Kevin")
        )

        self.assertTrue(result["ok"])
        self.assertIn("token", result)
        self.assertEqual(messaging.calls, [("ensure_recipient", "WhatsApp", "Kevin")])
        self.assertEqual(interaction.calls, [])  # verified, but not sent yet

    def test_prepare_with_unverified_recipient_refuses(self):
        interaction = RecordingLiveInteractionCapability()
        messaging = RecordingLiveMessagingCapability(verified=False)
        tools = self.make_tools(interaction, messaging)

        result = asyncio.run(
            tools["prepare_send_message"]("WhatsApp", "Salut", "Kevin")
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "recipient_not_verified")
        self.assertNotIn("token", result)
        self.assertEqual(interaction.calls, [])  # nothing prepared or sent

    def test_confirmation_has_its_own_lock(self):
        registry = ToolRegistry(interaction_capability=object())

        self.assertTrue(hasattr(registry.confirmation_lock, "acquire"))
        self.assertIsNot(registry.confirmation_lock, registry.interaction_lock)
