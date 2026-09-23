import unittest

from jarvis.capabilities.mouse import MouseCapability
from jarvis.security import SecurityDecision
from jarvis.tools.mouse import MouseError, MouseTools


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


class RecordingMouseTools:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.real_validator = MouseTools(backend=FakeMouseBackend())

    def validate_coordinates(self, x, y):
        return self.real_validator.validate_coordinates(x, y)

    def validate_scroll_direction(self, direction):
        return self.real_validator.validate_scroll_direction(direction)

    def validate_scroll_amount(self, amount):
        return self.real_validator.validate_scroll_amount(amount)

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def get_position(self):
        self.calls.append(("get_position",))
        self._raise_if_needed()
        return {
            "x": 10,
            "y": 20,
            "screen_index": 0,
        }

    def move(self, x, y):
        self.calls.append(("move", x, y))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": True,
            "previous_x": 10,
            "previous_y": 20,
            "target_x": x,
            "target_y": y,
            "x": x,
            "y": y,
            "screen_index": 0,
        }

    def click(self):
        self.calls.append(("click",))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": False,
            "button": "left",
            "click_count": 1,
            "x": 10,
            "y": 20,
            "screen_index": 0,
        }

    def double_click(self):
        self.calls.append(("double_click",))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": False,
            "button": "left",
            "click_count": 2,
            "x": 10,
            "y": 20,
            "screen_index": 0,
        }

    def right_click(self):
        self.calls.append(("right_click",))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": False,
            "button": "right",
            "click_count": 1,
            "x": 10,
            "y": 20,
            "screen_index": 0,
        }

    def scroll(self, direction, amount=3):
        self.calls.append(("scroll", direction, amount))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": False,
            "direction": direction,
            "amount": amount,
            "x": 10,
            "y": 20,
            "screen_index": 0,
        }


class FakeMouseBackend:
    def screens(self):
        return [
            {"screen_index": 0, "x": 0, "y": 0, "width": 1512, "height": 982},
        ]


class MouseCapabilityTest(unittest.TestCase):
    def test_get_mouse_position_reads_without_security(self):
        security = RecordingSecurity()
        tools = RecordingMouseTools()
        capability = MouseCapability(security=security, mouse_tools=tools)

        result = capability.get_mouse_position()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "get_mouse_position")
        self.assertEqual(result.data["x"], 10)
        self.assertEqual(result.data["y"], 20)
        self.assertEqual(result.data["screen_index"], 0)
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.calls, [("get_position",)])

    def test_move_mouse_uses_security_and_backend(self):
        security = RecordingSecurity()
        tools = RecordingMouseTools()
        capability = MouseCapability(security=security, mouse_tools=tools)

        result = capability.move_mouse(100, 200)

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(result.data["target_x"], 100)
        self.assertEqual(result.data["target_y"], 200)
        self.assertEqual(security.intents[0].action, "move_mouse")
        self.assertEqual(security.intents[0].target, "100,200")
        self.assertEqual(tools.calls, [("move", 100, 200)])

    def test_invalid_coordinates_do_not_use_security_or_backend(self):
        security = RecordingSecurity()
        tools = RecordingMouseTools()
        capability = MouseCapability(security=security, mouse_tools=tools)

        result = capability.move_mouse(True, 200)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_coordinates")
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.calls, [])

    def test_security_refusal_prevents_backend_command(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingMouseTools()
        capability = MouseCapability(security=security, mouse_tools=tools)

        result = capability.click()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(tools.calls, [])

    def test_security_confirmation_prevents_backend_command(self):
        security = RecordingSecurity(requires_confirmation=True)
        tools = RecordingMouseTools()
        capability = MouseCapability(security=security, mouse_tools=tools)

        result = capability.scroll("down", 3)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "confirmation_required")
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(tools.calls, [])

    def test_click_variants_return_unconfirmed_structured_results(self):
        tools = RecordingMouseTools()
        capability = MouseCapability(
            security=RecordingSecurity(),
            mouse_tools=tools,
        )

        click = capability.click()
        double_click = capability.double_click()
        right_click = capability.right_click()

        self.assertTrue(click.ok)
        self.assertFalse(click.data["state_confirmed"])
        self.assertEqual(click.data["button"], "left")
        self.assertEqual(double_click.data["click_count"], 2)
        self.assertEqual(right_click.data["button"], "right")
        self.assertEqual(
            tools.calls,
            [("click",), ("double_click",), ("right_click",)],
        )

    def test_scroll_uses_security_and_backend(self):
        security = RecordingSecurity()
        tools = RecordingMouseTools()
        capability = MouseCapability(security=security, mouse_tools=tools)

        result = capability.scroll("down", 4)

        self.assertTrue(result.ok)
        self.assertEqual(result.data["direction"], "down")
        self.assertEqual(result.data["amount"], 4)
        self.assertFalse(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "scroll")
        self.assertEqual(security.intents[0].target, "down:4")
        self.assertEqual(tools.calls, [("scroll", "down", 4)])

    def test_mouse_error_is_returned_explicitly(self):
        tools = RecordingMouseTools(
            error=MouseError("permission denied", "accessibility_permission_error"),
        )
        capability = MouseCapability(
            security=RecordingSecurity(),
            mouse_tools=tools,
        )

        result = capability.click()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "accessibility_permission_error")
        self.assertIn("permission denied", result.message)

    def test_unexpected_error_is_system_error(self):
        tools = RecordingMouseTools(error=RuntimeError("boom"))
        capability = MouseCapability(
            security=RecordingSecurity(),
            mouse_tools=tools,
        )

        result = capability.click()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")
        self.assertEqual(tools.calls, [("click",)])


if __name__ == "__main__":
    unittest.main()
