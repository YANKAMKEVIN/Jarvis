import unittest
import ctypes
from unittest.mock import Mock

from jarvis.tools.accessibility import (
    AccessibilityError,
    ApplicationServicesAccessibilityBackend,
    AccessibilityTools,
    match_elements,
    normalize_text,
)


class FakeAccessibilityBackend:
    def __init__(self, tree=None, trusted=True, errors=None):
        self.tree = tree or node("AXWindow", title="Main", children=[
            node("AXButton", title="Continuer", actions=["AXPress"]),
        ])
        self.trusted = trusted
        self.errors = errors or {}
        self.focused_calls = 0
        self.children_calls = []
        self.snapshots = []
        self.focus_calls = []
        self.press_calls = []
        self.released = []
        self.retained = []

    def focused_window(self):
        if not self.trusted:
            raise AccessibilityError(
                "Accessibility permission missing",
                "accessibility_permission_error",
            )

        self.focused_calls += 1
        return self.tree

    def element_snapshot(self, element, path):
        if tuple(path) in self.errors:
            raise self.errors[tuple(path)]

        self.snapshots.append((element.get("title"), list(path)))
        result = {
            key: value
            for key, value in element.items()
            if key != "children"
        }
        result["path"] = list(path)
        return result

    def children(self, element):
        self.children_calls.append(element.get("title"))
        return list(element.get("children", []))

    def set_focused(self, element):
        self.focus_calls.append(element.get("title"))
        element["focused"] = element.get("focus_confirms", True)

    def perform_press(self, element):
        self.press_calls.append(element.get("title"))

        if element.get("press_error"):
            raise element["press_error"]

        if element.get("role") == "AXCheckBox":
            element["selected"] = not element.get("selected", False)

    def retain(self, element):
        self.retained.append(element.get("title"))
        return element

    def release(self, element):
        if element is not None:
            self.released.append(element.get("title"))


class FakeFrontmostBackend(ApplicationServicesAccessibilityBackend):
    def __init__(
        self,
        candidates=None,
        windows_by_pid=None,
        trusted=True,
        system_error=None,
    ):
        self.candidates = candidates or []
        self.windows_by_pid = windows_by_pid or {}
        self.trusted = trusted
        self.system_error = system_error or AccessibilityError(
            "system cannot complete",
            "cannot_complete",
        )
        self.created_apps = []
        self.released = []
        self.visible_calls = 0
        self.system_calls = 0

    def ensure_trusted(self):
        if not self.trusted:
            raise AccessibilityError(
                "Accessibility permission missing",
                "accessibility_permission_error",
            )

    def _focused_window_from_system_wide(self):
        self.system_calls += 1
        raise self.system_error

    def visible_window_candidates(self):
        self.visible_calls += 1
        return [
            candidate
            for candidate in self.candidates
            if self.is_plausible_window_candidate(candidate)
        ]

    def create_application(self, pid):
        app = f"app:{pid}"
        self.created_apps.append(app)
        return app

    def copy_attribute(self, element, attribute):
        if attribute != "AXFocusedWindow":
            raise AssertionError(f"unexpected attribute {attribute}")

        pid = int(element.split(":", 1)[1])
        result = self.windows_by_pid.get(pid)

        if isinstance(result, AccessibilityError):
            raise result

        if result is None:
            raise AccessibilityError(
                "No focused window",
                "no_value",
            )

        return result

    def release(self, element):
        self.released.append(element)


def node(role, **kwargs):
    data = {
        "role": role,
        "enabled": True,
        "focused": False,
        "selected": False,
        "actions": [],
        "secure": role == "AXSecureTextField",
    }
    data.update(kwargs)
    return data


class AccessibilityToolsTest(unittest.TestCase):
    def test_editability_checks_settable_attribute_without_reading_value(self):
        for status, flag, expected in ((0, True, True), (0, False, False), (-25205, True, False)):
            with self.subTest(status=status, flag=flag):
                backend = object.__new__(ApplicationServicesAccessibilityBackend)
                backend.cf_string = Mock(return_value=42)
                backend.release = Mock()
                backend.copy_attribute = Mock(side_effect=AssertionError("Must not read value"))
                def check(element, attribute, output):
                    ctypes.cast(output, ctypes.POINTER(ctypes.c_bool))[0] = flag
                    return status
                backend.app_services = Mock()
                backend.app_services.AXUIElementIsAttributeSettable.side_effect = check
                self.assertEqual(backend.value_is_settable(123), expected)
                backend.cf_string.assert_called_once_with("AXValue")
                backend.release.assert_called_once_with(42)
                backend.copy_attribute.assert_not_called()

    def test_focused_window_falls_back_to_pid_when_system_path_cannot_complete(self):
        backend = FakeFrontmostBackend(
            candidates=[
                {"pid": 123, "owner": "Terminal", "layer": 0},
            ],
            windows_by_pid={123: "window:terminal"},
        )

        result = backend.focused_window()

        self.assertEqual(result, "window:terminal")
        self.assertEqual(backend.system_calls, 1)
        self.assertEqual(backend.visible_calls, 1)
        self.assertEqual(backend.created_apps, ["app:123"])
        self.assertEqual(backend.released, ["app:123"])

    def test_focused_window_skips_system_layers_and_selects_layer_zero_app(self):
        backend = FakeFrontmostBackend(
            candidates=[
                {"pid": 1, "owner": "Control Center", "layer": 25},
                {"pid": 2, "owner": "Window Server", "layer": 24},
                {"pid": 1261, "owner": "Terminal", "layer": 0},
            ],
            windows_by_pid={1261: "window:terminal"},
        )

        result = backend.focused_window()

        self.assertEqual(result, "window:terminal")
        self.assertEqual(backend.created_apps, ["app:1261"])

    def test_focused_window_tries_next_layer_zero_candidate_after_ax_failure(self):
        backend = FakeFrontmostBackend(
            candidates=[
                {"pid": 10, "owner": "First", "layer": 0},
                {"pid": 11, "owner": "Second", "layer": 0},
            ],
            windows_by_pid={
                10: AccessibilityError("cannot read", "cannot_complete"),
                11: "window:second",
            },
        )

        result = backend.focused_window()

        self.assertEqual(result, "window:second")
        self.assertEqual(backend.created_apps, ["app:10", "app:11"])
        self.assertEqual(backend.released, ["app:10", "app:11"])

    def test_focused_window_returns_structured_error_without_valid_candidate(self):
        backend = FakeFrontmostBackend(
            candidates=[
                {"pid": 1, "owner": "Window Server", "layer": 24},
                {"pid": 2, "owner": "Dock", "layer": 0},
            ],
            windows_by_pid={},
        )

        with self.assertRaises(AccessibilityError) as context:
            backend.focused_window()

        self.assertEqual(context.exception.code, "focused_window_unavailable")
        self.assertEqual(context.exception.data["system_error"], "cannot_complete")
        self.assertEqual(context.exception.data["fallback_error"], "no_accessibility_window")
        self.assertEqual(backend.created_apps, [])

    def test_focused_window_permission_refusal_happens_before_traversal(self):
        backend = FakeFrontmostBackend(
            candidates=[{"pid": 123, "owner": "Terminal", "layer": 0}],
            trusted=False,
        )

        with self.assertRaises(AccessibilityError) as context:
            backend.focused_window()

        self.assertEqual(context.exception.code, "accessibility_permission_error")
        self.assertEqual(backend.system_calls, 0)
        self.assertEqual(backend.visible_calls, 0)

    def test_inspect_ui_reads_bounded_tree(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", title="Main", children=[
            node("AXButton", title="Continuer", actions=["AXPress"]),
            node("AXTextField", title="Recherche", value_summary="hidden"),
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.inspect_ui(max_depth=2, max_elements=10)

        self.assertEqual(result["count"], 2)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["max_depth"], 2)
        self.assertEqual(result["max_elements"], 10)
        self.assertEqual(result["elements"][0]["title"], "Continuer")

    def test_inspect_ui_includes_search_fields_without_actions(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", title="Main", children=[
            node(
                "AXSearchField",
                description="Search or enter website name",
                actions=[],
            ),
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.inspect_ui(max_depth=2, max_elements=10)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["elements"][0]["role"], "AXSearchField")
        self.assertEqual(
            result["elements"][0]["description"],
            "Search or enter website name",
        )

    def test_permission_refusal_is_structured(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(trusted=False))

        with self.assertRaises(AccessibilityError) as context:
            tools.inspect_ui()

        self.assertEqual(context.exception.code, "accessibility_permission_error")

    def test_focus_reaches_search_field_at_recovery_depth(self):
        field = node("AXTextField", description="Search or enter website name")
        tree = field
        for _ in range(6):
            tree = node("AXGroup", children=[tree])
        backend = FakeAccessibilityBackend(tree=tree)
        tools = AccessibilityTools(backend=backend)

        self.assertEqual(tools.inspect_ui()["count"], 0)
        self.assertEqual(tools.inspect_ui(6, 150)["count"], 1)
        result = tools.focus_ui_element("Search or enter website name")

        self.assertTrue(result["state_confirmed"])
        self.assertEqual(len(backend.focus_calls), 1)

    def test_focus_reaches_search_field_after_default_element_limit(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            *[node("AXButton", title=f"Button {i}") for i in range(80)],
            node("AXTextField", title="Search"),
        ]))
        tools = AccessibilityTools(backend=backend)

        self.assertTrue(tools.inspect_ui()["truncated"])
        self.assertTrue(tools.focus_ui_element("Search")["state_confirmed"])

    def test_focus_checks_ambiguity_beyond_default_depth(self):
        deep = node("AXTextField", title="Search")
        for _ in range(5):
            deep = node("AXGroup", children=[deep])
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXTextField", title="Search"), deep,
        ]))

        with self.assertRaises(AccessibilityError) as context:
            AccessibilityTools(backend=backend).focus_ui_element("Search")

        self.assertEqual(context.exception.code, "ambiguous_ui_element")
        self.assertEqual(backend.focus_calls, [])

    def test_secure_text_field_does_not_expose_value(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXSecureTextField", title="Mot de passe", value_summary="secret"),
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.inspect_ui()

        self.assertTrue(result["elements"][0]["secure"])
        self.assertNotIn("value", result["elements"][0])
        self.assertNotIn("value_summary", result["elements"][0])

    def test_depth_limit_and_truncation(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXButton", title=f"Button {index}", actions=["AXPress"])
            for index in range(5)
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.inspect_ui(max_depth=1, max_elements=3)

        self.assertEqual(result["count"], 3)
        self.assertTrue(result["truncated"])

    def test_partial_ax_error_does_not_destroy_inspection(self):
        backend = FakeAccessibilityBackend(
            tree=node("AXWindow", children=[
                node("AXButton", title="OK", actions=["AXPress"]),
                node("AXButton", title="Boom", actions=["AXPress"]),
            ]),
            errors={(1,): AccessibilityError("bad child", "cannot_complete")},
        )
        tools = AccessibilityTools(backend=backend)

        result = tools.inspect_ui()

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["diagnostics"][0]["error_code"], "cannot_complete")

    def test_find_exact_and_accent_normalized(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXButton", title="Été Noël", actions=["AXPress"]),
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.find_ui_elements("ete noel")

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["title"], "Été Noël")

    def test_short_query_b_does_not_match_barre_by_substring(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node(
                "AXCheckBox",
                title="",
                description="barré",
                subrole="AXSegment",
                actions=["AXPress"],
            ),
        ])))

        with self.assertRaises(AccessibilityError) as context:
            tools.find_ui_elements("B")

        self.assertEqual(context.exception.code, "ui_element_not_found")

    def test_short_query_b_matches_exact_label(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXButton", title="B", actions=["AXPress"]),
            node("AXCheckBox", description="barré", actions=["AXPress"]),
        ])))

        result = tools.find_ui_elements("B")

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["title"], "B")

    def test_short_query_plus_matches_exact_label(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXButton", title="+", actions=["AXPress"]),
        ])))

        result = tools.find_ui_elements("+")

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["title"], "+")

    def test_short_query_plus_does_not_match_unrelated_text(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXButton", title="Ajouter", actions=["AXPress"]),
            node("AXStaticText", title="Aucun rapport"),
        ])))

        with self.assertRaises(AccessibilityError) as context:
            tools.find_ui_elements("+")

        self.assertEqual(context.exception.code, "ui_element_not_found")

    def test_normal_query_gras_matches_gras(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXCheckBox", description="gras", actions=["AXPress"]),
        ])))

        result = tools.find_ui_elements("gras")

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["description"], "gras")

    def test_normal_substring_query_still_matches_long_accessible_label(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXTextField", title="champ de recherche intelligente"),
        ])))

        result = tools.find_ui_elements("recherche")

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["title"], "champ de recherche intelligente")

    def test_find_role_filter(self):
        elements = [
            {"role": "AXButton", "title": "Recherche"},
            {"role": "AXTextField", "title": "Recherche"},
        ]

        matches = match_elements(elements, normalize_text("Recherche"), normalize_text("AXTextField"))

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["role"], "AXTextField")

    def test_find_no_result(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend())

        with self.assertRaises(AccessibilityError) as context:
            tools.find_ui_elements("Absent")

        self.assertEqual(context.exception.code, "ui_element_not_found")

    def test_focus_reresolves_and_confirms(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXTextField", title="Recherche"),
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.focus_ui_element("Recherche")

        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(backend.focus_calls, ["Recherche"])
        self.assertGreaterEqual(backend.focused_calls, 1)

    def test_focus_non_confirmed(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXTextField", title="Recherche", focus_confirms=False),
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.focus_ui_element("Recherche")

        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])

    def test_activate_requires_axpress(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXStaticText", title="Info"),
        ])))

        with self.assertRaises(AccessibilityError) as context:
            tools.activate_ui_element("Info")

        self.assertEqual(context.exception.code, "ui_action_unsupported")

    def test_activate_disabled_refuses(self):
        tools = AccessibilityTools(backend=FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXButton", title="Continuer", enabled=False, actions=["AXPress"]),
        ])))

        with self.assertRaises(AccessibilityError) as context:
            tools.activate_ui_element("Continuer")

        self.assertEqual(context.exception.code, "ui_element_disabled")

    def test_activate_button_is_executed_but_not_confirmed(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXButton", title="Continuer", actions=["AXPress"]),
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.activate_ui_element("Continuer")

        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(backend.press_calls, ["Continuer"])

    def test_activate_checkbox_can_be_confirmed_by_state_change(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXCheckBox", title="Se souvenir", selected=False, actions=["AXPress"]),
        ]))
        tools = AccessibilityTools(backend=backend)

        result = tools.activate_ui_element("Se souvenir")

        self.assertTrue(result["state_confirmed"])

    def test_activate_short_query_b_does_not_press_barre_false_positive(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node(
                "AXCheckBox",
                description="barré",
                subrole="AXSegment",
                actions=["AXPress"],
            ),
        ]))
        tools = AccessibilityTools(backend=backend)

        with self.assertRaises(AccessibilityError) as context:
            tools.activate_ui_element("B")

        self.assertEqual(context.exception.code, "ui_element_not_found")
        self.assertEqual(backend.press_calls, [])

    def test_ambiguous_resolution_prevents_action(self):
        backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
            node("AXButton", title="Continuer", actions=["AXPress"]),
            node("AXButton", title="Continuer", actions=["AXPress"]),
        ]))
        tools = AccessibilityTools(backend=backend)

        with self.assertRaises(AccessibilityError) as context:
            tools.activate_ui_element("Continuer")

        self.assertEqual(context.exception.code, "ambiguous_ui_element")
        self.assertEqual(backend.press_calls, [])


if __name__ == "__main__":
    unittest.main()
