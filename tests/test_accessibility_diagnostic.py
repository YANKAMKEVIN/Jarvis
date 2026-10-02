import json
import unittest

from scripts.diagnose_accessibility import AppWindowBackend, inspect_limits
from tests.test_accessibility_tools import FakeAccessibilityBackend, node


class AccessibilityDiagnosticTest(unittest.TestCase):
    def test_reports_limits_and_field_metadata_without_values_or_window_titles(self):
        field = node(
            "AXTextField", title="Search", subrole="AXSearchField",
            description="Search or enter website name", identifier="address",
            value="PRIVATE_VALUE", value_summary="PRIVATE_SUMMARY",
        )
        nested = field
        for _ in range(5):
            nested = node("AXGroup", children=[nested])
        backend = FakeAccessibilityBackend(tree=node(
            "AXWindow", title="PRIVATE_WINDOW", children=[
                node("AXSecureTextField", title="PRIVATE_SECURE"), nested,
            ],
        ))

        reports = inspect_limits(backend)

        self.assertEqual(reports[0]["fields"], [])
        self.assertEqual(reports[1]["fields"][0]["subrole"], "AXSearchField")
        self.assertEqual(len(reports[1]["fields"][0]["path"]), 6)
        self.assertNotIn("PRIVATE", json.dumps(reports))
        self.assertEqual(backend.focus_calls, [])
        self.assertEqual(backend.press_calls, [])

    def test_targets_requested_app_without_system_wide_fallback(self):
        class Backend(AppWindowBackend):
            def __init__(self):
                self.pid = 123
                self.calls = []

            def ensure_trusted(self):
                self.calls.append("trusted")

            def create_application(self, pid):
                self.calls.append(pid)
                return "app"

            def copy_attribute(self, app, attribute):
                self.calls.append((app, attribute))
                return "window"

            def release(self, handle):
                self.calls.append(("release", handle))

        backend = Backend()
        self.assertEqual(backend.focused_window(), "window")
        self.assertEqual(backend.calls, [
            "trusted", 123, ("app", "AXFocusedWindow"), ("release", "app"),
        ])
