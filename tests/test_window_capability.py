import unittest

from jarvis.capabilities.windows import WindowCapability
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
        window_state=None,
        action_state=None,
        error=None,
    ):
        self.window_state = window_state or {
            "target_app": "Safari",
            "frontmost": True,
            "window_title": "Example",
            "position": {"x": 0, "y": 25},
            "size": {"width": 800, "height": 600},
            "minimized": False,
            "fullscreen": False,
        }
        self.action_state = action_state or {
            **self.window_state,
            "command_executed": True,
            "state_confirmed": True,
            "previous_position": {"x": 100, "y": 100},
            "previous_size": {"width": 600, "height": 400},
        }
        self.error = error
        self.active_calls = 0
        self.focus_calls = []
        self.minimize_calls = []
        self.maximize_calls = []
        self.move_calls = []

    def get_active_window(self):
        self.active_calls += 1

        if self.error is not None:
            raise self.error

        return dict(self.window_state)

    def focus_window(self, app_name):
        self.focus_calls.append(app_name)

        if self.error is not None:
            raise self.error

        return dict(self.action_state)

    def minimize_window(self, app_name=None):
        self.minimize_calls.append(app_name)

        if self.error is not None:
            raise self.error

        return dict(self.action_state)

    def maximize_window(self, app_name=None):
        self.maximize_calls.append(app_name)

        if self.error is not None:
            raise self.error

        return dict(self.action_state)

    def move_window(self, position, app_name=None):
        self.move_calls.append((position, app_name))

        if self.error is not None:
            raise self.error

        return dict(self.action_state)


class WindowCapabilityTest(unittest.TestCase):
    def test_get_active_window_success_does_not_use_security(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = WindowCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.get_active_window()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "get_active_window")
        self.assertEqual(result.data["target_app"], "Safari")
        self.assertEqual(result.data["window_title"], "Example")
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.active_calls, 1)

    def test_focus_window_success_uses_security_and_backend(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = WindowCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.focus_window(" Safari ")

        self.assertTrue(result.ok)
        self.assertEqual(security.intents[0].action, "focus_window")
        self.assertEqual(security.intents[0].target, "Safari")
        self.assertEqual(tools.focus_calls, ["Safari"])

    def test_minimize_window_can_target_active_window(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = WindowCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.minimize_window()

        self.assertTrue(result.ok)
        self.assertEqual(security.intents[0].target, "active_window")
        self.assertEqual(tools.minimize_calls, [None])

    def test_maximize_window_state_not_confirmed_uses_prudent_message(self):
        tools = RecordingMacOSTools(
            action_state={
                "target_app": "Visual Studio Code",
                "frontmost": True,
                "window_title": "main.py",
                "position": {"x": 10, "y": 40},
                "size": {"width": 500, "height": 300},
                "minimized": False,
                "fullscreen": False,
                "command_executed": True,
                "state_confirmed": False,
                "previous_position": {"x": 20, "y": 50},
                "previous_size": {"width": 400, "height": 300},
            }
        )
        capability = WindowCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.maximize_window("Visual Studio Code")

        self.assertTrue(result.ok)
        self.assertFalse(result.data["state_confirmed"])
        self.assertIn("pas pu confirmer", result.message)

    def test_move_window_accepts_supported_positions(self):
        for position in ("left", "right", "center", "fullscreen"):
            with self.subTest(position=position):
                tools = RecordingMacOSTools()
                capability = WindowCapability(
                    security=RecordingSecurity(),
                    macos_tools=tools,
                )

                result = capability.move_window(position, "Safari")

                self.assertTrue(result.ok)
                self.assertEqual(tools.move_calls, [(position, "Safari")])

    def test_move_window_rejects_invalid_position_before_security_or_backend(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = WindowCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.move_window("top", "Safari")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_window_position")
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.move_calls, [])

    def test_security_refusal_does_not_call_backend(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingMacOSTools()
        capability = WindowCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.move_window("left", "Safari")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(tools.move_calls, [])

    def test_no_window_error_is_explicit(self):
        capability = WindowCapability(
            security=RecordingSecurity(),
            macos_tools=RecordingMacOSTools(
                error=RuntimeError("Aucune fenetre manipulable."),
            ),
        )

        result = capability.minimize_window("Safari")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "no_window")
        self.assertIn("Aucune fenetre", result.message)

    def test_accessibility_error_is_explicit_system_failure(self):
        capability = WindowCapability(
            security=RecordingSecurity(),
            macos_tools=RecordingMacOSTools(
                error=RuntimeError("System Events erreur -10827"),
            ),
        )

        result = capability.get_active_window()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")
        self.assertIn("-10827", result.message)


if __name__ == "__main__":
    unittest.main()


class ArrangeWindowsTest(unittest.TestCase):
    def test_tiles_two_apps_left_and_right(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        cap = WindowCapability(security=security, macos_tools=tools)

        result = cap.arrange_side_by_side("Safari", "Notes")

        self.assertTrue(result.ok)
        self.assertEqual(tools.move_calls, [("left", "Safari"), ("right", "Notes")])
        self.assertEqual(result.data["left_app"], "Safari")
        self.assertEqual(result.data["right_app"], "Notes")

    def test_requires_both_apps(self):
        cap = WindowCapability(security=RecordingSecurity(), macos_tools=RecordingMacOSTools())
        self.assertFalse(cap.arrange_side_by_side("Safari", "  ").ok)
        self.assertFalse(cap.arrange_side_by_side("", "Notes").ok)

    def test_stops_if_left_move_fails(self):
        security = RecordingSecurity(allowed=False)  # move blocked -> left fails
        cap = WindowCapability(security=security, macos_tools=RecordingMacOSTools())
        result = cap.arrange_side_by_side("Safari", "Notes")
        self.assertFalse(result.ok)
