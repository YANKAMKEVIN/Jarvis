import unittest

from jarvis.capabilities.apps import AppCapability
from jarvis.security import SecurityDecision


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


class RecordingMacOSTools:
    def __init__(
        self,
        running=True,
        open_error=None,
        close_error=None,
        running_error=None,
    ):
        self.running = running
        self.open_error = open_error
        self.close_error = close_error
        self.running_error = running_error
        self.open_calls = []
        self.close_calls = []
        self.running_calls = []

    def open_app(self, app_name):
        self.open_calls.append(app_name)

        if self.open_error is not None:
            raise self.open_error

        return f"{app_name} a ete ouvert."

    def close_app(self, app_name):
        self.close_calls.append(app_name)

        if self.close_error is not None:
            raise self.close_error

        return f"{app_name} a ete ferme."

    def is_app_running(self, app_name):
        self.running_calls.append(app_name)

        if self.running_error is not None:
            raise self.running_error

        return self.running


class AppCapabilityTest(unittest.TestCase):
    def test_open_app_success_uses_security_then_macos(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = AppCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.open_app(" Safari ")

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "open_app")
        self.assertEqual(result.data, {"target": "Safari"})
        self.assertEqual(result.message, "Safari a ete ouvert.")
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "open_app")
        self.assertEqual(security.intents[0].target, "Safari")
        self.assertEqual(tools.open_calls, ["Safari"])

    def test_close_app_success_uses_security_then_macos(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = AppCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.close_app("Spotify")

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "close_app")
        self.assertEqual(result.data, {"target": "Spotify"})
        self.assertEqual(result.message, "Spotify a ete ferme.")
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "close_app")
        self.assertEqual(security.intents[0].target, "Spotify")
        self.assertEqual(tools.close_calls, ["Spotify"])

    def test_is_app_running_true_does_not_require_security(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools(running=True)
        capability = AppCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.is_app_running("Safari")

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "is_app_running")
        self.assertEqual(result.data, {"target": "Safari", "running": True})
        self.assertEqual(result.message, "Safari est actuellement ouvert.")
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.running_calls, ["Safari"])

    def test_is_app_running_false_does_not_require_security(self):
        tools = RecordingMacOSTools(running=False)
        capability = AppCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.is_app_running("Spotify")

        self.assertTrue(result.ok)
        self.assertEqual(result.data, {"target": "Spotify", "running": False})
        self.assertEqual(result.message, "Spotify n'est pas ouvert actuellement.")

    def test_empty_app_name_is_rejected_without_security_or_macos(self):
        for method_name in ("open_app", "close_app", "is_app_running"):
            with self.subTest(method_name=method_name):
                security = RecordingSecurity()
                tools = RecordingMacOSTools()
                capability = AppCapability(
                    security=security,
                    macos_tools=tools,
                )

                result = getattr(capability, method_name)("   ")

                self.assertFalse(result.ok)
                self.assertEqual(result.error_code, "invalid_app_name")
                self.assertEqual(security.intents, [])
                self.assertEqual(tools.open_calls, [])
                self.assertEqual(tools.close_calls, [])
                self.assertEqual(tools.running_calls, [])

    def test_non_string_app_name_is_rejected(self):
        capability = AppCapability(
            security=RecordingSecurity(),
            macos_tools=RecordingMacOSTools(),
        )

        result = capability.open_app(None)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_app_name")

    def test_security_refusal_does_not_call_macos(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingMacOSTools()
        capability = AppCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.open_app("Safari")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(tools.open_calls, [])

    def test_macos_exception_returns_failure(self):
        tools = RecordingMacOSTools(
            close_error=RuntimeError("quit failed"),
        )
        capability = AppCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.close_app("Spotify")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")
        self.assertIn("quit failed", result.message)
        self.assertEqual(tools.close_calls, ["Spotify"])


if __name__ == "__main__":
    unittest.main()
