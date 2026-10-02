import unittest

from jarvis.capabilities.interaction import InteractionCapability
from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.tools.accessibility import AccessibilityTools
from tests.test_accessibility_tools import FakeAccessibilityBackend, node
from tests.test_ui_accessibility_capability import RecordingSecurity


def success(action, **data):
    return ToolResult.success(action=action, message=f"{action} ok", **data)


def failure(action, error_code="boom"):
    return ToolResult.failure(
        action=action,
        message=f"{action} failed",
        error_code=error_code,
    )


class RecordingApps:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def open_app(self, app_name):
        self.calls.append(("open_app", app_name))
        return self.result or success("open_app", target=app_name)


class RecordingWindows:
    def __init__(
        self,
        focus_result=None,
        focus_results=None,
        active_result=None,
    ):
        self.focus_result = focus_result
        self.focus_results = list(focus_results or [])
        self.active_result = active_result
        self.calls = []

    def focus_window(self, app_name):
        self.calls.append(("focus_window", app_name))

        if self.focus_results:
            return self.focus_results.pop(0)

        return self.focus_result or success(
            "focus_window",
            command_executed=True,
            state_confirmed=True,
            target_app=app_name,
            window_title="Example",
        )

    def get_active_window(self):
        self.calls.append(("get_active_window",))
        return self.active_result or success(
            "get_active_window",
            target_app="Safari",
            window_title="Example",
        )


class RecordingUI:
    def __init__(self, focus_results=None, inspect_result=None):
        self.focus_results = list(focus_results or [])
        self.inspect_result = inspect_result
        self.calls = []

    def focus_ui_element(self, query, role=None):
        self.calls.append(("focus_ui_element", query, role))

        if self.focus_results:
            return self.focus_results.pop(0)

        return success(
            "focus_ui_element",
            command_executed=True,
            state_confirmed=True,
            query_length=len(query),
            role=role,
        )

    def inspect_ui(self, max_depth=4, max_elements=80):
        self.calls.append(("inspect_ui", max_depth, max_elements))
        return self.inspect_result or success(
            "inspect_ui",
            elements=[],
            count=0,
            truncated=False,
        )


class RecordingKeyboard:
    def __init__(
        self,
        hotkey_results=None,
        type_result=None,
        enter_result=None,
    ):
        self.hotkey_results = list(hotkey_results or [])
        self.type_result = type_result
        self.enter_result = enter_result
        self.calls = []

    def hotkey(self, keys):
        self.calls.append(("hotkey", list(keys)))

        if self.hotkey_results:
            return self.hotkey_results.pop(0)

        return success(
            "hotkey",
            command_executed=True,
            state_confirmed=False,
            keys=list(keys),
            target_app="Safari",
            target_window="Example",
        )

    def type_text(self, text):
        self.calls.append(("type_text", text))
        return self.type_result or success(
            "type_text",
            command_executed=True,
            state_confirmed=False,
            length=len(text),
            target_app="Safari",
            target_window="Example",
        )

    def press_key(self, key):
        self.calls.append(("press_key", key))
        return self.enter_result or success(
            "press_key",
            command_executed=True,
            state_confirmed=False,
            key=key,
            target_app="Safari",
            target_window="Example",
        )


class RecordingClipboard:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def get_clipboard_text(self):
        self.calls.append(("get_clipboard_text",))

        if self.results:
            return self.results.pop(0)

        return success(
            "get_clipboard_text",
            has_text=True,
            text="clipboard text",
            length=len("clipboard text"),
            returned_length=len("clipboard text"),
            truncated=False,
            content_type="text",
        )


class InteractionCapabilityTest(unittest.TestCase):
    def test_real_metadata_matching_and_recovery_before_typing(self):
        for fields in (
            {"description": "champ de recherche intelligente"},
            {"identifier": "WEB_BROWSER_ADDRESS_AND_SEARCH_FIELD"},
            {"identifier": "OTHER_SEARCH_INPUT"},
        ):
            for count in (0, 1, 2):
                with self.subTest(fields=fields, count=count):
                    backend = FakeAccessibilityBackend(tree=node("AXWindow", children=[
                        node("AXTextField", **fields) for _ in range(count)
                    ]))
                    ui = UIAccessibilityCapability(
                        security=RecordingSecurity(),
                        accessibility_tools=AccessibilityTools(backend=backend),
                    )
                    keyboard = RecordingKeyboard()
                    result = self.make_capability(ui=ui, keyboard=keyboard).focus_app_ui_and_type(
                        "Safari", "OpenAI", query="recherche", press_enter=True,
                    )
                    self.assertEqual(result.ok, count == 1)
                    self.assertEqual(keyboard.calls, [
                        ("type_text", "OpenAI"), ("press_key", "enter"),
                    ] if count == 1 else [])
                    if count == 1:
                        self.assertFalse(result.data["state_confirmed"])
                        names = [step["name"] for step in result.data["steps"]]
                        self.assertEqual(names[:3], ["open_app", "focus_window", "get_active_window"])
                        self.assertEqual(names[-2:], ["type_text", "press_key_enter"])
                        self.assertTrue(backend.focus_calls)
                    else:
                        self.assertEqual(result.error_code,
                            "ambiguous_ui_element" if count == 2 else "ui_element_not_found")

    def test_query_none_requires_observed_editable_focus(self):
        base = dict(role="AXTextArea", focused=True, enabled=True, editable=True)
        for changes, accepted in (
            ({}, True), ({"focused": False}, False), ({"editable": False}, False),
            ({"editable": None}, False), ({"enabled": False}, False),
            ({"role": "AXButton"}, False), ({"secure": True}, False),
            ({"subrole": "AXSecureTextField"}, False),
        ):
            with self.subTest(changes=changes):
                ui = RecordingUI(inspect_result=success("inspect_ui", elements=[
                    {**base, **changes, "title": "PRIVATE_LABEL", "value": "PRIVATE_VALUE"},
                ], truncated=False))
                keyboard = RecordingKeyboard()
                windows = RecordingWindows(active_result=success("get_active_window", target_app="TextEdit"))
                result = self.make_capability(ui=ui, windows=windows, keyboard=keyboard).focus_app_ui_and_type(
                    "TextEdit", "Bonjour", press_enter=True,
                )
                self.assertEqual(result.ok, accepted)
                self.assertNotIn("PRIVATE", str(result.to_livekit_dict()))
                self.assertEqual(keyboard.calls, [
                    ("type_text", "Bonjour"), ("press_key", "enter"),
                ] if accepted else [])
                if not accepted:
                    self.assertEqual(result.error_code, "editable_target_not_verified")
                    self.assertTrue(result.data["command_executed"])
                    self.assertFalse(result.data["text_command_executed"])

    def test_query_none_rejects_incomplete_missing_or_ambiguous_observation(self):
        field = dict(role="AXTextField", focused=True, enabled=True, editable=True)
        for observation in (
            success("inspect_ui", elements=[]),
            success("inspect_ui", elements=[field, field]),
            success("inspect_ui", elements=[field], truncated=True),
            success("inspect_ui", elements=[field], diagnostics=[{"error_code": "cannot_complete"}]),
            failure("inspect_ui", "accessibility_permission_error"),
        ):
            keyboard = RecordingKeyboard()
            result = self.make_capability(
                ui=RecordingUI(inspect_result=observation), keyboard=keyboard,
            ).focus_app_ui_and_type("Safari", "OpenAI", press_enter=True)
            self.assertEqual(result.error_code, "editable_target_not_verified")
            self.assertEqual(keyboard.calls, [])

    def test_enter_requires_explicitly_executed_typing(self):
        for typed in (
            failure("type_text"), success("type_text", command_executed=False),
            success("type_text"),
        ):
            keyboard = RecordingKeyboard(type_result=typed)
            result = self.make_capability(keyboard=keyboard).focus_app_ui_and_type(
                "Safari", "OpenAI", query="recherche", press_enter=True,
            )
            self.assertFalse(result.ok)
            self.assertEqual(keyboard.calls, [("type_text", "OpenAI")])

    def make_capability(
        self,
        apps=None,
        windows=None,
        ui=None,
        keyboard=None,
        clipboard=None,
        readiness_attempts=3,
        readiness_delay_seconds=0,
        sleeper=None,
    ):
        return InteractionCapability(
            apps=apps or RecordingApps(),
            windows=windows or RecordingWindows(),
            ui_accessibility=ui or RecordingUI(),
            keyboard=keyboard or RecordingKeyboard(),
            clipboard=clipboard or RecordingClipboard(),
            readiness_attempts=readiness_attempts,
            readiness_delay_seconds=readiness_delay_seconds,
            sleeper=sleeper or (lambda seconds: None),
        )

    def test_select_all_and_copy_runs_hotkeys_in_order(self):
        keyboard = RecordingKeyboard()
        clipboard = RecordingClipboard(results=[
            success(
                "get_clipboard_text",
                has_text=False,
                length=0,
                returned_length=0,
                truncated=False,
                content_type="no_text_detected",
            ),
            success(
                "get_clipboard_text",
                has_text=True,
                text="copied",
                length=6,
                returned_length=6,
                truncated=False,
                content_type="text",
            ),
        ])
        capability = self.make_capability(keyboard=keyboard, clipboard=clipboard)

        result = capability.select_all_and_copy()

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertTrue(result.data["state_confirmed"])
        self.assertTrue(result.data["clipboard_verified"])
        self.assertTrue(result.data["clipboard_has_text"])
        self.assertEqual(result.data["clipboard_length"], 6)
        self.assertTrue(result.data["copy_observed"])
        self.assertTrue(result.data["new_copy_proven"])
        self.assertEqual(
            keyboard.calls,
            [
                ("hotkey", ["command", "a"]),
                ("hotkey", ["command", "c"]),
            ],
        )
        self.assertEqual(
            [step["name"] for step in result.data["steps"]],
            [
                "get_clipboard_text_before",
                "hotkey_command_a",
                "hotkey_command_c",
                "get_clipboard_text_after",
            ],
        )
        self.assertEqual(
            clipboard.calls,
            [("get_clipboard_text",), ("get_clipboard_text",)],
        )

    def test_select_all_and_copy_stops_when_select_fails(self):
        keyboard = RecordingKeyboard(
            hotkey_results=[failure("hotkey", "select_failed")],
        )
        clipboard = RecordingClipboard()
        capability = self.make_capability(keyboard=keyboard, clipboard=clipboard)

        result = capability.select_all_and_copy()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "select_failed")
        self.assertEqual(result.data["failed_step"], "hotkey_command_a")
        self.assertEqual(keyboard.calls, [("hotkey", ["command", "a"])])
        self.assertEqual(clipboard.calls, [("get_clipboard_text",)])

    def test_select_all_and_copy_stops_when_select_is_not_executed(self):
        keyboard = RecordingKeyboard(
            hotkey_results=[
                success("hotkey", command_executed=False, state_confirmed=False),
            ],
        )
        capability = self.make_capability(keyboard=keyboard)

        result = capability.select_all_and_copy()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "command_not_executed")
        self.assertEqual(keyboard.calls, [("hotkey", ["command", "a"])])

    def test_select_all_and_copy_allows_unconfirmed_command_a(self):
        keyboard = RecordingKeyboard(
            hotkey_results=[
                success("hotkey", command_executed=True, state_confirmed=False),
                success("hotkey", command_executed=True, state_confirmed=False),
            ],
        )
        capability = self.make_capability(keyboard=keyboard)

        result = capability.select_all_and_copy()

        self.assertTrue(result.ok)
        self.assertEqual(len(keyboard.calls), 2)

    def test_select_all_and_copy_does_not_confirm_when_copy_fails(self):
        keyboard = RecordingKeyboard(
            hotkey_results=[
                success("hotkey", command_executed=True, state_confirmed=False),
                failure("hotkey", "copy_failed"),
            ],
        )
        clipboard = RecordingClipboard()
        capability = self.make_capability(keyboard=keyboard, clipboard=clipboard)

        result = capability.select_all_and_copy()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "copy_failed")
        self.assertEqual(result.data["failed_step"], "hotkey_command_c")
        self.assertEqual(clipboard.calls, [("get_clipboard_text",)])

    def test_select_all_and_copy_does_not_confirm_when_after_read_fails(self):
        keyboard = RecordingKeyboard()
        clipboard = RecordingClipboard(results=[
            success("get_clipboard_text", has_text=False),
            failure("get_clipboard_text", "clipboard_read_failed"),
        ])
        capability = self.make_capability(keyboard=keyboard, clipboard=clipboard)

        result = capability.select_all_and_copy()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "clipboard_read_failed")
        self.assertFalse(result.data["clipboard_verified"])
        self.assertFalse(result.data["clipboard_has_text"])

    def test_select_all_and_copy_reports_empty_clipboard_after_copy(self):
        clipboard = RecordingClipboard(results=[
            success("get_clipboard_text", has_text=False),
            success("get_clipboard_text", has_text=False, length=0),
        ])
        capability = self.make_capability(clipboard=clipboard)

        result = capability.select_all_and_copy()

        self.assertTrue(result.ok)
        self.assertFalse(result.data["state_confirmed"])
        self.assertTrue(result.data["clipboard_verified"])
        self.assertFalse(result.data["clipboard_has_text"])

    def test_select_all_and_copy_does_not_confirm_identical_clipboard(self):
        clipboard = RecordingClipboard(results=[
            success("get_clipboard_text", has_text=True, text="same", length=4),
            success("get_clipboard_text", has_text=True, text="same", length=4),
        ])
        capability = self.make_capability(clipboard=clipboard)

        result = capability.select_all_and_copy()

        self.assertTrue(result.ok)
        self.assertFalse(result.data["state_confirmed"])
        self.assertTrue(result.data["clipboard_verified"])
        self.assertTrue(result.data["clipboard_has_text"])
        self.assertFalse(result.data["clipboard_changed"])
        self.assertFalse(result.data["copy_observed"])
        self.assertFalse(result.data["new_copy_proven"])

    def test_select_all_and_copy_does_not_expose_clipboard_text(self):
        clipboard = RecordingClipboard(results=[
            success("get_clipboard_text", has_text=True, text="SECRET_OLD", length=10),
            success("get_clipboard_text", has_text=True, text="SECRET_NEW", length=10),
        ])
        capability = self.make_capability(clipboard=clipboard)

        result = capability.select_all_and_copy()

        payload = str(result.to_livekit_dict())

        self.assertNotIn("SECRET_OLD", payload)
        self.assertNotIn("SECRET_NEW", payload)

    def test_focus_app_ui_and_type_runs_strict_sequence(self):
        apps = RecordingApps()
        windows = RecordingWindows()
        ui = RecordingUI()
        keyboard = RecordingKeyboard()
        capability = self.make_capability(
            apps=apps,
            windows=windows,
            ui=ui,
            keyboard=keyboard,
        )

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
            role="AXTextField",
            press_enter=True,
        )

        self.assertTrue(result.ok)
        self.assertEqual(apps.calls, [("open_app", "Safari")])
        self.assertEqual(
            windows.calls,
            [("focus_window", "Safari"), ("get_active_window",)],
        )
        self.assertEqual(
            ui.calls,
            [("focus_ui_element", "barre de recherche", "AXTextField")],
        )
        self.assertEqual(
            keyboard.calls,
            [("type_text", "OpenAI"), ("press_key", "enter")],
        )
        self.assertEqual(result.data["text_length"], len("OpenAI"))
        self.assertNotIn("text", result.data)

    def test_focus_app_ui_and_type_stops_when_open_app_fails(self):
        apps = RecordingApps(result=failure("open_app", "app_missing"))
        keyboard = RecordingKeyboard()
        capability = self.make_capability(apps=apps, keyboard=keyboard)

        result = capability.focus_app_ui_and_type("Safari", "OpenAI")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "app_missing")
        self.assertEqual(result.data["failed_step"], "open_app")
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_never_types_when_focus_window_unconfirmed(self):
        windows = RecordingWindows(
            focus_result=success(
                "focus_window",
                command_executed=True,
                state_confirmed=False,
                target_app="Safari",
            ),
        )
        keyboard = RecordingKeyboard()
        capability = self.make_capability(windows=windows, keyboard=keyboard)

        result = capability.focus_app_ui_and_type("Safari", "OpenAI")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "state_not_confirmed")
        self.assertEqual(result.data["failed_step"], "focus_window")
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_never_types_when_active_window_mismatches(self):
        windows = RecordingWindows(
            active_result=success(
                "get_active_window",
                target_app="JARVIS",
                window_title="Chat",
            ),
        )
        keyboard = RecordingKeyboard()
        capability = self.make_capability(windows=windows, keyboard=keyboard)

        result = capability.focus_app_ui_and_type("Safari", "OpenAI")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "active_window_mismatch")
        self.assertEqual(result.data["failed_step"], "get_active_window")
        self.assertEqual(result.data["observed_app"], "JARVIS")
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_retries_temporary_no_window_after_open(self):
        apps = RecordingApps()
        windows = RecordingWindows(
            focus_results=[
                failure("focus_window", "no_window"),
                success(
                    "focus_window",
                    command_executed=True,
                    state_confirmed=True,
                    target_app="Safari",
                ),
            ],
            active_result=success(
                "get_active_window",
                target_app="Safari",
                window_title="Example",
            ),
        )
        keyboard = RecordingKeyboard()
        sleeps = []
        capability = self.make_capability(
            apps=apps,
            windows=windows,
            keyboard=keyboard,
            readiness_attempts=2,
            readiness_delay_seconds=0.1,
            sleeper=sleeps.append,
        )

        result = capability.focus_app_ui_and_type("Safari", "OpenAI", query="recherche")

        self.assertTrue(result.ok)
        self.assertEqual(apps.calls, [("open_app", "Safari")])
        self.assertEqual(
            windows.calls,
            [
                ("focus_window", "Safari"),
                ("focus_window", "Safari"),
                ("get_active_window",),
            ],
        )
        self.assertEqual(sleeps, [0.1])
        self.assertEqual(keyboard.calls, [("type_text", "OpenAI")])

    def test_focus_app_ui_and_type_readiness_timeout_does_not_type(self):
        windows = RecordingWindows(
            focus_results=[
                failure("focus_window", "no_window"),
                failure("focus_window", "no_window"),
            ],
        )
        keyboard = RecordingKeyboard()
        sleeps = []
        capability = self.make_capability(
            windows=windows,
            keyboard=keyboard,
            readiness_attempts=2,
            readiness_delay_seconds=0.1,
            sleeper=sleeps.append,
        )

        result = capability.focus_app_ui_and_type("Safari", "OpenAI")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "no_window")
        self.assertEqual(result.data["failed_step"], "focus_window")
        self.assertEqual(
            windows.calls,
            [("focus_window", "Safari"), ("focus_window", "Safari")],
        )
        self.assertEqual(sleeps, [0.1])
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_does_not_retry_non_readiness_error(self):
        windows = RecordingWindows(
            focus_results=[failure("focus_window", "security_denied")],
        )
        keyboard = RecordingKeyboard()
        capability = self.make_capability(windows=windows, keyboard=keyboard)

        result = capability.focus_app_ui_and_type("Safari", "OpenAI")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(windows.calls, [("focus_window", "Safari")])
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_does_not_duplicate_mutating_actions_during_readiness(self):
        apps = RecordingApps()
        windows = RecordingWindows(
            focus_results=[
                failure("focus_window", "no_window"),
                success(
                    "focus_window",
                    command_executed=True,
                    state_confirmed=True,
                    target_app="Safari",
                ),
            ],
        )
        ui = RecordingUI()
        keyboard = RecordingKeyboard()
        capability = self.make_capability(
            apps=apps,
            windows=windows,
            ui=ui,
            keyboard=keyboard,
            readiness_attempts=2,
        )

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
            press_enter=True,
        )

        self.assertTrue(result.ok)
        self.assertEqual(apps.calls, [("open_app", "Safari")])
        self.assertEqual(ui.calls, [("focus_ui_element", "barre de recherche", None)])
        self.assertEqual(
            keyboard.calls,
            [("type_text", "OpenAI"), ("press_key", "enter")],
        )

    def test_focus_app_ui_and_type_never_types_when_ui_target_missing(self):
        ui = RecordingUI(
            focus_results=[failure("focus_ui_element", "ui_element_not_found")],
        )
        keyboard = RecordingKeyboard()
        windows = RecordingWindows(
            active_result=success(
                "get_active_window",
                target_app="Safari",
                window_title="Example",
            ),
        )
        capability = self.make_capability(
            windows=windows,
            ui=ui,
            keyboard=keyboard,
        )

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ui_element_not_found")
        self.assertEqual(result.data["failed_step"], "focus_ui_element")
        self.assertEqual(keyboard.calls, [])
        self.assertEqual(
            ui.calls,
            [
                ("focus_ui_element", "barre de recherche", None),
                ("inspect_ui", 6, 150),
            ],
        )

    def test_focus_app_ui_and_type_never_types_when_ui_focus_unconfirmed(self):
        ui = RecordingUI(
            focus_results=[
                success(
                    "focus_ui_element",
                    command_executed=True,
                    state_confirmed=False,
                ),
            ],
        )
        keyboard = RecordingKeyboard()
        windows = RecordingWindows(
            active_result=success(
                "get_active_window",
                target_app="Safari",
                window_title="Example",
            ),
        )
        capability = self.make_capability(
            windows=windows,
            ui=ui,
            keyboard=keyboard,
        )

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "state_not_confirmed")
        self.assertEqual(result.data["failed_step"], "focus_ui_element")
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_recovery_finds_unique_search_field(self):
        ui = RecordingUI(
            focus_results=[
                failure("focus_ui_element", "ui_element_not_found"),
                success(
                    "focus_ui_element",
                    command_executed=True,
                    state_confirmed=True,
                ),
            ],
            inspect_result=success(
                "inspect_ui",
                elements=[
                    {"role": "AXButton", "title": "Partager"},
                    {
                        "role": "AXTextField",
                        "title": "champ de recherche intelligente",
                    },
                ],
                count=2,
                truncated=False,
            ),
        )
        keyboard = RecordingKeyboard()
        windows = RecordingWindows(
            active_result=success(
                "get_active_window",
                target_app="Safari",
                window_title="Example",
            ),
        )
        capability = self.make_capability(
            windows=windows,
            ui=ui,
            keyboard=keyboard,
        )

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
            role="AXTextField",
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            ui.calls,
            [
                ("focus_ui_element", "barre de recherche", "AXTextField"),
                ("inspect_ui", 6, 150),
                (
                    "focus_ui_element",
                    "champ de recherche intelligente",
                    "AXTextField",
                ),
            ],
        )
        self.assertEqual(keyboard.calls, [("type_text", "OpenAI")])
        self.assertIn("focus_ui_element_recovery", [
            step["name"] for step in result.data["steps"]
        ])

    def test_focus_app_ui_and_type_recovery_finds_unique_ax_search_field(self):
        ui = RecordingUI(
            focus_results=[
                failure("focus_ui_element", "ui_element_not_found"),
                success(
                    "focus_ui_element",
                    command_executed=True,
                    state_confirmed=True,
                ),
            ],
            inspect_result=success(
                "inspect_ui",
                elements=[
                    {"role": "AXButton", "title": "Partager"},
                    {
                        "role": "AXSearchField",
                        "description": "Search or enter website name",
                        "actions": ["AXConfirm"],
                    },
                ],
                count=2,
                truncated=False,
            ),
        )
        keyboard = RecordingKeyboard()
        capability = self.make_capability(ui=ui, keyboard=keyboard)

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            ui.calls,
            [
                ("focus_ui_element", "barre de recherche", None),
                ("inspect_ui", 6, 150),
                ("focus_ui_element", "Search or enter website name", None),
            ],
        )
        self.assertEqual(keyboard.calls, [("type_text", "OpenAI")])

    def test_focus_app_ui_and_type_recovery_no_candidate_does_not_type(self):
        ui = RecordingUI(
            focus_results=[failure("focus_ui_element", "ui_element_not_found")],
            inspect_result=success(
                "inspect_ui",
                elements=[{"role": "AXButton", "title": "Partager"}],
            ),
        )
        keyboard = RecordingKeyboard()
        capability = self.make_capability(ui=ui, keyboard=keyboard)

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ui_element_not_found")
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_recovery_ambiguous_does_not_type(self):
        ui = RecordingUI(
            focus_results=[failure("focus_ui_element", "ui_element_not_found")],
            inspect_result=success(
                "inspect_ui",
                elements=[
                    {"role": "AXTextField", "title": "champ de recherche"},
                    {"role": "AXTextField", "title": "recherche intelligente"},
                ],
            ),
        )
        keyboard = RecordingKeyboard()
        windows = RecordingWindows(
            active_result=success(
                "get_active_window",
                target_app="Safari",
                window_title="Example",
            ),
        )
        capability = self.make_capability(
            windows=windows,
            ui=ui,
            keyboard=keyboard,
        )

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ambiguous_ui_element")
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_recovered_focus_unconfirmed_does_not_type(self):
        ui = RecordingUI(
            focus_results=[
                failure("focus_ui_element", "ui_element_not_found"),
                success(
                    "focus_ui_element",
                    command_executed=True,
                    state_confirmed=False,
                ),
            ],
            inspect_result=success(
                "inspect_ui",
                elements=[{"role": "AXTextField", "title": "champ de recherche"}],
            ),
        )
        keyboard = RecordingKeyboard()
        windows = RecordingWindows(
            active_result=success(
                "get_active_window",
                target_app="Safari",
                window_title="Example",
            ),
        )
        capability = self.make_capability(
            windows=windows,
            ui=ui,
            keyboard=keyboard,
        )

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "state_not_confirmed")
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_does_not_recover_other_ui_errors(self):
        ui = RecordingUI(
            focus_results=[failure("focus_ui_element", "accessibility_permission_error")],
        )
        keyboard = RecordingKeyboard()
        windows = RecordingWindows(
            active_result=success(
                "get_active_window",
                target_app="Safari",
                window_title="Example",
            ),
        )
        capability = self.make_capability(
            windows=windows,
            ui=ui,
            keyboard=keyboard,
        )

        result = capability.focus_app_ui_and_type(
            "Safari",
            "OpenAI",
            query="barre de recherche",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "accessibility_permission_error")
        self.assertEqual(ui.calls, [("focus_ui_element", "barre de recherche", None)])
        self.assertEqual(keyboard.calls, [])

    def test_focus_app_ui_and_type_short_query_b_does_not_recover_barre(self):
        ui = RecordingUI(
            focus_results=[failure("focus_ui_element", "ui_element_not_found")],
            inspect_result=success(
                "inspect_ui",
                elements=[{"role": "AXCheckBox", "description": "barré"}],
            ),
        )
        keyboard = RecordingKeyboard()
        windows = RecordingWindows(
            active_result=success(
                "get_active_window",
                target_app="TextEdit",
                window_title="Untitled",
            ),
        )
        capability = self.make_capability(
            windows=windows,
            ui=ui,
            keyboard=keyboard,
        )

        result = capability.focus_app_ui_and_type("TextEdit", "x", query="B")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ui_element_not_found")
        self.assertEqual(keyboard.calls, [])

    def test_open_app_and_focus_ui_does_not_type(self):
        ui = RecordingUI()
        keyboard = RecordingKeyboard()
        capability = self.make_capability(ui=ui, keyboard=keyboard)

        result = capability.open_app_and_focus_ui(
            "Safari",
            "barre de recherche",
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(ui.calls, [("focus_ui_element", "barre de recherche", None)])
        self.assertEqual(keyboard.calls, [])

    def test_interaction_steps_do_not_include_raw_text_or_query(self):
        capability = self.make_capability()

        result = capability.focus_app_ui_and_type(
            "Safari",
            "SECRET_TEXT",
            query="SECRET_QUERY",
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.data["text_length"], len("SECRET_TEXT"))
        self.assertEqual(result.data["query_length"], len("SECRET_QUERY"))
        self.assertNotIn("SECRET_TEXT", str(result.to_livekit_dict()))
        self.assertNotIn("SECRET_QUERY", str(result.to_livekit_dict()))


if __name__ == "__main__":
    unittest.main()
