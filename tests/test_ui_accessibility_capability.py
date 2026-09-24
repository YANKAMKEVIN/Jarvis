import unittest

from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.security import SecurityDecision
from jarvis.tools.accessibility import AccessibilityError


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


class RecordingAccessibilityTools:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def inspect_ui(self, max_depth=4, max_elements=80):
        self.calls.append(("inspect_ui", max_depth, max_elements))
        self._raise_if_needed()
        return {
            "elements": [{"role": "AXButton", "title": "Continuer"}],
            "count": 1,
            "truncated": False,
            "max_depth": max_depth,
            "max_elements": max_elements,
        }

    def find_ui_elements(self, query, role=None):
        self.calls.append(("find_ui_elements", query, role))
        self._raise_if_needed()
        return {
            "query_length": len(query),
            "role": role,
            "candidates": [{"role": role or "AXButton", "title": "Continuer"}],
            "candidate_count": 1,
            "truncated": False,
        }

    def focus_ui_element(self, query, role=None):
        self.calls.append(("focus_ui_element", query, role))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": True,
            "candidate": {"role": role or "AXTextField", "title": query},
            "element": {"role": role or "AXTextField", "title": query, "focused": True},
        }

    def activate_ui_element(self, query, role=None):
        self.calls.append(("activate_ui_element", query, role))
        self._raise_if_needed()
        return {
            "command_executed": True,
            "state_confirmed": False,
            "candidate": {"role": role or "AXButton", "title": query},
            "element": {"role": role or "AXButton", "title": query},
        }


class UIAccessibilityCapabilityTest(unittest.TestCase):
    def test_inspect_ui_does_not_use_security(self):
        security = RecordingSecurity()
        tools = RecordingAccessibilityTools()
        capability = UIAccessibilityCapability(
            security=security,
            accessibility_tools=tools,
        )

        result = capability.inspect_ui(3, 20)

        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.calls, [("inspect_ui", 3, 20)])

    def test_find_one_candidate(self):
        tools = RecordingAccessibilityTools()
        capability = UIAccessibilityCapability(
            security=RecordingSecurity(),
            accessibility_tools=tools,
        )

        result = capability.find_ui_elements("Continuer", "AXButton")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["candidate_count"], 1)
        self.assertEqual(tools.calls, [("find_ui_elements", "Continuer", "AXButton")])

    def test_find_ambiguous_returns_failure(self):
        class AmbiguousTools(RecordingAccessibilityTools):
            def find_ui_elements(self, query, role=None):
                self.calls.append(("find_ui_elements", query, role))
                return {
                    "query_length": len(query),
                    "role": role,
                    "candidates": [{"title": "A"}, {"title": "A"}],
                    "candidate_count": 2,
                    "truncated": False,
                }

        capability = UIAccessibilityCapability(
            security=RecordingSecurity(),
            accessibility_tools=AmbiguousTools(),
        )

        result = capability.find_ui_elements("A")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ambiguous_ui_element")

    def test_focus_uses_security_and_backend(self):
        security = RecordingSecurity()
        tools = RecordingAccessibilityTools()
        capability = UIAccessibilityCapability(
            security=security,
            accessibility_tools=tools,
        )

        result = capability.focus_ui_element("Recherche", "AXTextField")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "focus_ui_element")
        self.assertEqual(tools.calls, [("focus_ui_element", "Recherche", "AXTextField")])

    def test_activate_uses_security_and_keeps_state_unconfirmed(self):
        security = RecordingSecurity()
        tools = RecordingAccessibilityTools()
        capability = UIAccessibilityCapability(
            security=security,
            accessibility_tools=tools,
        )

        result = capability.activate_ui_element("Continuer")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertFalse(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "activate_ui_element")
        self.assertEqual(tools.calls, [("activate_ui_element", "Continuer", None)])

    def test_security_refusal_prevents_backend_action(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingAccessibilityTools()
        capability = UIAccessibilityCapability(
            security=security,
            accessibility_tools=tools,
        )

        result = capability.activate_ui_element("Continuer")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(tools.calls, [])

    def test_security_confirmation_prevents_backend_action(self):
        security = RecordingSecurity(requires_confirmation=True)
        tools = RecordingAccessibilityTools()
        capability = UIAccessibilityCapability(
            security=security,
            accessibility_tools=tools,
        )

        result = capability.focus_ui_element("Recherche")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "confirmation_required")
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(tools.calls, [])

    def test_accessibility_error_is_structured(self):
        tools = RecordingAccessibilityTools(
            error=AccessibilityError("permission", "accessibility_permission_error"),
        )
        capability = UIAccessibilityCapability(
            security=RecordingSecurity(),
            accessibility_tools=tools,
        )

        result = capability.inspect_ui()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "accessibility_permission_error")

    def test_unexpected_error_is_system_error(self):
        tools = RecordingAccessibilityTools(error=RuntimeError("boom"))
        capability = UIAccessibilityCapability(
            security=RecordingSecurity(),
            accessibility_tools=tools,
        )

        result = capability.inspect_ui()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")


if __name__ == "__main__":
    unittest.main()
