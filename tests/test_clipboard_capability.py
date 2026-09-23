import unittest

from jarvis.capabilities.clipboard import ClipboardCapability
from jarvis.security import SecurityDecision
from jarvis.tools.clipboard import ClipboardError, MAX_RETURN_CHARS


class RecordingSecurity:
    def __init__(self, allowed=True, requires_confirmation=False):
        self.allowed = allowed
        self.requires_confirmation = requires_confirmation
        self.intents = []

    def evaluate(self, intent):
        self.intents.append(intent)
        return SecurityDecision(
            allowed=self.allowed,
            requires_confirmation=self.requires_confirmation,
            reason="test security",
        )


class RecordingClipboardTools:
    def __init__(
        self,
        text_state=None,
        set_state=None,
        clear_state=None,
        error=None,
    ):
        self.text_state = text_state or {
            "has_text": True,
            "text": "Bonjour",
            "length": 7,
            "returned_length": 7,
            "truncated": False,
            "content_type": "text",
        }
        self.set_state = set_state or {
            "command_executed": True,
            "state_confirmed": True,
            "length": 7,
            "has_text": True,
            "content_type": "text",
        }
        self.clear_state = clear_state or {
            "command_executed": True,
            "state_confirmed": True,
            "has_text": False,
            "length": 0,
            "content_type": "no_text_detected",
        }
        self.error = error
        self.calls = []

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def get_text(self):
        self.calls.append(("get_text",))
        self._raise_if_needed()
        return dict(self.text_state)

    def set_text(self, text):
        self.calls.append(("set_text", text))
        self._raise_if_needed()
        return dict(self.set_state)

    def clear(self):
        self.calls.append(("clear",))
        self._raise_if_needed()
        return dict(self.clear_state)


class ClipboardCapabilityTest(unittest.TestCase):
    def test_get_clipboard_text_does_not_use_security(self):
        security = RecordingSecurity()
        tools = RecordingClipboardTools()
        capability = ClipboardCapability(security=security, clipboard_tools=tools)

        result = capability.get_clipboard_text()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "get_clipboard_text")
        self.assertEqual(result.data["text"], "Bonjour")
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.calls, [("get_text",)])

    def test_get_clipboard_text_no_text_detected(self):
        capability = ClipboardCapability(
            security=RecordingSecurity(),
            clipboard_tools=RecordingClipboardTools(
                text_state={
                    "has_text": False,
                    "text": None,
                    "length": 0,
                    "returned_length": 0,
                    "truncated": False,
                    "content_type": "no_text_detected",
                }
            ),
        )

        result = capability.get_clipboard_text()

        self.assertTrue(result.ok)
        self.assertFalse(result.data["has_text"])
        self.assertIn("texte lisible", result.message)

    def test_get_clipboard_text_long_text_is_reported_as_truncated(self):
        capability = ClipboardCapability(
            security=RecordingSecurity(),
            clipboard_tools=RecordingClipboardTools(
                text_state={
                    "has_text": True,
                    "text": "a" * MAX_RETURN_CHARS,
                    "length": MAX_RETURN_CHARS + 10,
                    "returned_length": MAX_RETURN_CHARS,
                    "truncated": True,
                    "content_type": "text",
                }
            ),
        )

        result = capability.get_clipboard_text()

        self.assertTrue(result.ok)
        self.assertTrue(result.data["truncated"])
        self.assertIn("trop long", result.message)

    def test_set_clipboard_text_uses_security_and_preserves_confirmation(self):
        security = RecordingSecurity()
        tools = RecordingClipboardTools()
        capability = ClipboardCapability(security=security, clipboard_tools=tools)

        result = capability.set_clipboard_text("Bonjour")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "set_clipboard_text")
        self.assertEqual(tools.calls, [("set_text", "Bonjour")])

    def test_set_clipboard_text_unconfirmed_state_is_not_announced_as_success(self):
        capability = ClipboardCapability(
            security=RecordingSecurity(),
            clipboard_tools=RecordingClipboardTools(
                set_state={
                    "command_executed": True,
                    "state_confirmed": False,
                    "length": 7,
                    "has_text": True,
                    "content_type": "text",
                }
            ),
        )

        result = capability.set_clipboard_text("Bonjour")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertFalse(result.data["state_confirmed"])
        self.assertIn("pas pu confirmer", result.message)

    def test_set_clipboard_text_long_value_can_be_confirmed_without_returning_text(self):
        long_text = "a" * (MAX_RETURN_CHARS + 20)
        capability = ClipboardCapability(
            security=RecordingSecurity(),
            clipboard_tools=RecordingClipboardTools(
                set_state={
                    "command_executed": True,
                    "state_confirmed": True,
                    "length": len(long_text),
                    "has_text": True,
                    "content_type": "text",
                }
            ),
        )

        result = capability.set_clipboard_text(long_text)

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(result.data["length"], len(long_text))
        self.assertNotIn("text", result.data)

    def test_clear_clipboard_uses_security_and_preserves_confirmation(self):
        security = RecordingSecurity()
        tools = RecordingClipboardTools()
        capability = ClipboardCapability(security=security, clipboard_tools=tools)

        result = capability.clear_clipboard()

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "clear_clipboard")
        self.assertEqual(tools.calls, [("clear",)])

    def test_clear_clipboard_unconfirmed_state_is_not_announced_as_success(self):
        capability = ClipboardCapability(
            security=RecordingSecurity(),
            clipboard_tools=RecordingClipboardTools(
                clear_state={
                    "command_executed": True,
                    "state_confirmed": False,
                    "has_text": True,
                    "length": 5,
                    "content_type": "text",
                }
            ),
        )

        result = capability.clear_clipboard()

        self.assertTrue(result.ok)
        self.assertFalse(result.data["state_confirmed"])
        self.assertIn("pas pu confirmer", result.message)

    def test_security_refusal_prevents_mutation(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingClipboardTools()
        capability = ClipboardCapability(security=security, clipboard_tools=tools)

        result = capability.set_clipboard_text("Bonjour")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(tools.calls, [])

    def test_security_confirmation_prevents_mutation(self):
        security = RecordingSecurity(requires_confirmation=True)
        tools = RecordingClipboardTools()
        capability = ClipboardCapability(security=security, clipboard_tools=tools)

        result = capability.clear_clipboard()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "confirmation_required")
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(tools.calls, [])

    def test_clipboard_error_is_returned_explicitly(self):
        capability = ClipboardCapability(
            security=RecordingSecurity(),
            clipboard_tools=RecordingClipboardTools(
                error=ClipboardError("pbpaste failed", "clipboard_read_error")
            ),
        )

        result = capability.get_clipboard_text()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "clipboard_read_error")
        self.assertIn("pbpaste failed", result.message)

    def test_unexpected_error_is_system_error(self):
        capability = ClipboardCapability(
            security=RecordingSecurity(),
            clipboard_tools=RecordingClipboardTools(error=RuntimeError("boom")),
        )

        result = capability.get_clipboard_text()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")


if __name__ == "__main__":
    unittest.main()
