import unittest

from jarvis.capabilities.system import SystemCapability
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
        battery=None,
        system_info=None,
        brightness=50,
        battery_error=None,
        system_error=None,
        brightness_error=None,
        set_brightness_error=None,
        lock_error=None,
        lock_state=None,
    ):
        self.battery = battery or {
            "percentage": 74,
            "charging": True,
            "charged": False,
            "external_power": True,
            "raw": "test battery",
        }
        self.system_info = system_info or {
            "model_name": "MacBook Pro",
            "model_identifier": "Mac15,3",
            "chip": "Apple M3",
            "memory": "8 GB",
            "serial_number": "TEST123",
        }
        self.brightness = brightness
        self.battery_error = battery_error
        self.system_error = system_error
        self.brightness_error = brightness_error
        self.set_brightness_error = set_brightness_error
        self.lock_error = lock_error
        self.lock_state = lock_state or {
            "command_executed": True,
            "state_confirmed": False,
            "locked": None,
            "backend": "test_backend",
        }
        self.battery_calls = 0
        self.system_info_calls = 0
        self.get_brightness_calls = 0
        self.set_brightness_calls = []
        self.lock_calls = 0

    def get_battery_status(self):
        self.battery_calls += 1

        if self.battery_error is not None:
            raise self.battery_error

        return dict(self.battery)

    def get_system_info(self):
        self.system_info_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return dict(self.system_info)

    def get_brightness(self):
        self.get_brightness_calls += 1

        if self.brightness_error is not None:
            raise self.brightness_error

        return self.brightness

    def set_brightness(self, level):
        self.set_brightness_calls.append(level)

        if self.set_brightness_error is not None:
            raise self.set_brightness_error

        return {
            "requested_brightness": level,
            "brightness": level,
        }

    def lock_screen(self):
        self.lock_calls += 1

        if self.lock_error is not None:
            raise self.lock_error

        return dict(self.lock_state)


class SystemCapabilityTest(unittest.TestCase):
    def test_get_battery_status_success_charging(self):
        tools = RecordingMacOSTools()
        capability = SystemCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.get_battery_status()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "get_battery_status")
        self.assertEqual(result.data["percentage"], 74)
        self.assertTrue(result.data["charging"])
        self.assertIn("en charge", result.message)
        self.assertEqual(tools.battery_calls, 1)

    def test_get_battery_status_success_not_charging(self):
        tools = RecordingMacOSTools(
            battery={
                "percentage": 42,
                "charging": False,
                "charged": False,
                "external_power": False,
                "raw": "test battery",
            }
        )
        capability = SystemCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.get_battery_status()

        self.assertTrue(result.ok)
        self.assertEqual(result.data["percentage"], 42)
        self.assertFalse(result.data["charging"])

    def test_get_battery_status_error(self):
        capability = SystemCapability(
            security=RecordingSecurity(),
            macos_tools=RecordingMacOSTools(
                battery_error=RuntimeError("pmset failed"),
            ),
        )

        result = capability.get_battery_status()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")
        self.assertIn("pmset failed", result.message)

    def test_get_system_info_success(self):
        tools = RecordingMacOSTools()
        capability = SystemCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.get_system_info()

        self.assertTrue(result.ok)
        self.assertEqual(result.data["model_name"], "MacBook Pro")
        self.assertEqual(result.data["chip"], "Apple M3")
        self.assertIn("MacBook Pro", result.message)
        self.assertEqual(tools.system_info_calls, 1)

    def test_get_brightness_success(self):
        tools = RecordingMacOSTools(brightness=67)
        capability = SystemCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.get_brightness()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "get_brightness")
        self.assertEqual(result.data, {"brightness": 67})
        self.assertEqual(tools.get_brightness_calls, 1)

    def test_set_brightness_success_uses_security_and_backend_once(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = SystemCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.set_brightness(30)

        self.assertTrue(result.ok)
        self.assertEqual(result.data["requested_brightness"], 30)
        self.assertEqual(result.data["brightness"], 30)
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "set_brightness")
        self.assertEqual(security.intents[0].target, "30")
        self.assertEqual(tools.set_brightness_calls, [30])

    def test_set_brightness_rejects_out_of_range_without_security_or_backend(self):
        for level in (-1, 101):
            with self.subTest(level=level):
                security = RecordingSecurity()
                tools = RecordingMacOSTools()
                capability = SystemCapability(
                    security=security,
                    macos_tools=tools,
                )

                result = capability.set_brightness(level)

                self.assertFalse(result.ok)
                self.assertEqual(result.error_code, "brightness_out_of_range")
                self.assertEqual(security.intents, [])
                self.assertEqual(tools.set_brightness_calls, [])

    def test_set_brightness_security_refusal_does_not_call_backend(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingMacOSTools()
        capability = SystemCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.set_brightness(30)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(tools.set_brightness_calls, [])

    def test_lock_screen_command_sent_without_confirmed_state(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = SystemCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.lock_screen()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "lock_screen")
        self.assertTrue(result.data["command_executed"])
        self.assertFalse(result.data["state_confirmed"])
        self.assertIsNone(result.data["locked"])
        self.assertIn("pas pu confirmer", result.message)
        self.assertEqual(security.intents[0].action, "lock_screen")
        self.assertEqual(tools.lock_calls, 1)

    def test_lock_screen_confirmed_success_only_when_backend_confirms_state(self):
        tools = RecordingMacOSTools(
            lock_state={
                "command_executed": True,
                "state_confirmed": True,
                "locked": True,
                "backend": "test_backend",
            }
        )
        capability = SystemCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.lock_screen()

        self.assertTrue(result.ok)
        self.assertTrue(result.data["locked"])
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(result.message, "Mac verrouille.")

    def test_lock_screen_failure(self):
        capability = SystemCapability(
            security=RecordingSecurity(),
            macos_tools=RecordingMacOSTools(
                lock_error=RuntimeError("lock failed"),
            ),
        )

        result = capability.lock_screen()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")
        self.assertIn("lock failed", result.message)


if __name__ == "__main__":
    unittest.main()
