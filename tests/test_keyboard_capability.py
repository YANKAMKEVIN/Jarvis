import unittest

from jarvis.capabilities.keyboard import KeyboardCapability
from jarvis.security import SecurityDecision
from jarvis.tools.keyboard import KeyboardError, KeyboardTools


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


class RecordingKeyboardTools:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.real_validator = KeyboardTools()

    def validate_type_text(self, text):
        return self.real_validator.validate_type_text(text)

    def validate_key(self, key):
        return self.real_validator.validate_key(key)

    def validate_hotkey(self, keys):
        return self.real_validator.validate_hotkey(keys)

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def type_text(self, text):
        self.calls.append(("type_text", text))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": False,
            "length": len(text),
            "line_count": text.count("\n") + 1,
            "target_app": "Safari",
            "target_window": "Example",
        }

    def press_key(self, key):
        self.calls.append(("press_key", key))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": False,
            "key": key,
            "target_app": "Safari",
            "target_window": "Example",
        }

    def hotkey(self, keys):
        self.calls.append(("hotkey", keys))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": False,
            "keys": list(keys),
            "target_app": "Safari",
            "target_window": "Example",
        }


class KeyboardCapabilityTest(unittest.TestCase):
    def test_type_text_uses_security_and_backend_without_returning_raw_text(self):
        security = RecordingSecurity()
        tools = RecordingKeyboardTools()
        capability = KeyboardCapability(security=security, keyboard_tools=tools)

        result = capability.type_text("Bonjour secret")

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "type_text")
        self.assertTrue(result.data["command_executed"])
        self.assertFalse(result.data["state_confirmed"])
        self.assertEqual(result.data["length"], len("Bonjour secret"))
        self.assertNotIn("text", result.data)
        self.assertIn("ne peut pas confirmer", result.message)
        self.assertEqual(security.intents[0].action, "type_text")
        self.assertEqual(security.intents[0].target, f"length:{len('Bonjour secret')}")
        self.assertEqual(tools.calls, [("type_text", "Bonjour secret")])

    def test_press_key_uses_security_and_backend(self):
        security = RecordingSecurity()
        tools = RecordingKeyboardTools()
        capability = KeyboardCapability(security=security, keyboard_tools=tools)

        result = capability.press_key("entrée")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["key"], "enter")
        self.assertFalse(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "press_key")
        self.assertEqual(security.intents[0].target, "enter")
        self.assertEqual(tools.calls, [("press_key", "enter")])

    def test_hotkey_uses_security_and_backend(self):
        security = RecordingSecurity()
        tools = RecordingKeyboardTools()
        capability = KeyboardCapability(security=security, keyboard_tools=tools)

        result = capability.hotkey(["cmd", "shift", "z"])

        self.assertTrue(result.ok)
        self.assertEqual(result.data["keys"], ["command", "shift", "z"])
        self.assertFalse(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "hotkey")
        self.assertEqual(security.intents[0].target, "command+shift+z")
        self.assertEqual(tools.calls, [("hotkey", ["command", "shift", "z"])])

    def test_compact_hotkey_is_normalized_before_security_and_backend(self):
        security = RecordingSecurity()
        tools = RecordingKeyboardTools()
        capability = KeyboardCapability(security=security, keyboard_tools=tools)

        result = capability.hotkey(["command+a"])

        self.assertTrue(result.ok)
        self.assertEqual(result.data["keys"], ["command", "a"])
        self.assertEqual(security.intents[0].target, "command+a")
        self.assertEqual(tools.calls, [("hotkey", ["command", "a"])])

    def test_invalid_arguments_do_not_use_security_or_backend(self):
        security = RecordingSecurity()
        tools = RecordingKeyboardTools()
        capability = KeyboardCapability(security=security, keyboard_tools=tools)

        result = capability.hotkey(["command", "q"])

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "hotkey_not_allowed")
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.calls, [])

    def test_security_refusal_prevents_backend_command(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingKeyboardTools()
        capability = KeyboardCapability(security=security, keyboard_tools=tools)

        result = capability.press_key("enter")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(tools.calls, [])

    def test_security_confirmation_prevents_backend_command(self):
        security = RecordingSecurity(requires_confirmation=True)
        tools = RecordingKeyboardTools()
        capability = KeyboardCapability(security=security, keyboard_tools=tools)

        result = capability.type_text("Bonjour")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "confirmation_required")
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(tools.calls, [])

    def test_keyboard_error_is_returned_explicitly(self):
        tools = RecordingKeyboardTools(
            error=KeyboardError("permission denied", "accessibility_permission_error"),
        )
        capability = KeyboardCapability(
            security=RecordingSecurity(),
            keyboard_tools=tools,
        )

        result = capability.press_key("enter")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "accessibility_permission_error")
        self.assertIn("permission denied", result.message)

    def test_unexpected_error_is_system_error(self):
        tools = RecordingKeyboardTools(error=RuntimeError("boom"))
        capability = KeyboardCapability(
            security=RecordingSecurity(),
            keyboard_tools=tools,
        )

        result = capability.press_key("enter")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")
        self.assertEqual(tools.calls, [("press_key", "enter")])


if __name__ == "__main__":
    unittest.main()
