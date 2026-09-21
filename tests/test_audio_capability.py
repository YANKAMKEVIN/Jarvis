import unittest

from jarvis.capabilities.audio import AudioCapability
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
    def __init__(self, volume=40, set_error=None, get_error=None):
        self.volume = volume
        self.set_error = set_error
        self.get_error = get_error
        self.set_calls = []
        self.get_calls = 0

    def set_volume(self, level):
        self.set_calls.append(level)

        if self.set_error is not None:
            raise self.set_error

        return f"Volume regle a {level} %."

    def get_volume(self):
        self.get_calls += 1

        if self.get_error is not None:
            raise self.get_error

        return self.volume


class AudioCapabilityTest(unittest.TestCase):
    def test_get_volume_returns_tool_result_success(self):
        tools = RecordingMacOSTools(volume=31)
        capability = AudioCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.get_volume()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "get_volume")
        self.assertEqual(result.data, {"volume": 31})
        self.assertEqual(result.message, "Le volume actuel est de 31 %.")
        self.assertEqual(tools.get_calls, 1)

    def test_get_volume_returns_tool_result_failure(self):
        capability = AudioCapability(
            security=RecordingSecurity(),
            macos_tools=RecordingMacOSTools(
                get_error=RuntimeError("osascript failed"),
            ),
        )

        result = capability.get_volume()

        self.assertFalse(result.ok)
        self.assertEqual(result.action, "get_volume")
        self.assertEqual(result.error_code, "system_error")
        self.assertEqual(result.data, {})
        self.assertIn("osascript failed", result.message)

    def test_set_volume_validates_and_calls_security_then_macos(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = AudioCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.set_volume(60)

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "set_volume")
        self.assertEqual(result.data, {"volume": 60})
        self.assertEqual(result.message, "Volume regle a 60 %.")
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "set_volume")
        self.assertEqual(security.intents[0].target, "60")
        self.assertEqual(tools.set_calls, [60])

    def test_set_volume_accepts_boundaries(self):
        for volume in (0, 100):
            with self.subTest(volume=volume):
                tools = RecordingMacOSTools()
                capability = AudioCapability(
                    security=RecordingSecurity(),
                    macos_tools=tools,
                )

                result = capability.set_volume(volume)

                self.assertTrue(result.ok)
                self.assertEqual(result.data, {"volume": volume})
                self.assertEqual(tools.set_calls, [volume])

    def test_set_volume_rejects_out_of_range_without_security_or_macos(self):
        for volume in (-1, 101):
            with self.subTest(volume=volume):
                security = RecordingSecurity()
                tools = RecordingMacOSTools()
                capability = AudioCapability(
                    security=security,
                    macos_tools=tools,
                )

                result = capability.set_volume(volume)

                self.assertFalse(result.ok)
                self.assertEqual(result.error_code, "volume_out_of_range")
                self.assertEqual(security.intents, [])
                self.assertEqual(tools.set_calls, [])

    def test_set_volume_security_refusal_does_not_call_macos(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingMacOSTools()
        capability = AudioCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.set_volume(40)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(tools.set_calls, [])

    def test_set_volume_macos_failure_returns_tool_result_failure(self):
        tools = RecordingMacOSTools(set_error=RuntimeError("osascript failed"))
        capability = AudioCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.set_volume(40)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")
        self.assertEqual(tools.set_calls, [40])
        self.assertIn("osascript failed", result.message)


if __name__ == "__main__":
    unittest.main()
