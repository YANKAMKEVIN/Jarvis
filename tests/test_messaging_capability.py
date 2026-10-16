import unittest

from jarvis.capabilities.messaging import MessagingCapability
from jarvis.capabilities.results import ToolResult


# Mirrors WhatsApp's real structure: the open conversation's recipient is the
# description of the NavigationBar_HeaderViewButton; message bubbles carry their
# own text (and names) in description but must never be used to verify.
def header(description="Joel Chinda"):
    return {
        "role": "AXButton",
        "identifier": "NavigationBar_HeaderViewButton",
        "description": description,
    }


def message_bubble(description):
    return {
        "role": "AXStaticText",
        "identifier": "WAMessageBubbleTableViewCell",
        "description": description,
    }


class FakeWindows:
    def __init__(self, active=None, focus_confirmed=True):
        self.active = active or ToolResult.success(
            action="get_active_window", message="ok", target_app="WhatsApp",
        )
        self.focus_confirmed = focus_confirmed
        self.calls = []

    def get_active_window(self):
        return self.active

    def focus_window(self, app_name):
        self.calls.append(("focus_window", app_name))
        return ToolResult.success(
            action="focus_window", message="ok",
            state_confirmed=self.focus_confirmed, target_app=app_name,
        )


class FakeUI:
    def __init__(self, elements=None, inspect=None, inspects=None, focus_confirmed=True,
                 send_button_present=True, composer_value_after=""):
        if inspects is not None:
            self._inspects = list(inspects)
        elif inspect is not None:
            self._inspects = [inspect]
        else:
            self._inspects = [ToolResult.success(
                action="inspect_ui", message="ok",
                elements=elements if elements is not None else [header()],
                truncated=False,
            )]
        self.focus_confirmed = focus_confirmed
        self.send_button_present = send_button_present
        self.composer_value_after = composer_value_after
        self.calls = []

    def set_value(self, query, value, role=None):
        self.calls.append(("set_value", query, value))
        return ToolResult.success(
            action="set_value", message="ok",
            command_executed=True, state_confirmed=True,
        )

    def activate_ui_element(self, query, role=None):
        self.calls.append(("activate_ui_element", query))
        if query == "ChatBar_SendButton" and not self.send_button_present:
            return ToolResult(
                ok=False, action="activate_ui_element", message="ko",
                data={}, error_code="ui_element_not_found",
            )
        return ToolResult.success(
            action="activate_ui_element", message="ok",
            command_executed=True, state_confirmed=False,
        )

    def read_value(self, query, role=None):
        self.calls.append(("read_value", query))
        return ToolResult.success(
            action="read_value", message="ok", value=self.composer_value_after,
        )

    def inspect_ui(self, max_depth=4, max_elements=80):
        self.calls.append(("inspect_ui", max_depth, max_elements))
        if len(self._inspects) > 1:
            return self._inspects.pop(0)
        return self._inspects[0]

    def focus_ui_element(self, query, role=None):
        self.calls.append(("focus_ui_element", query, role))
        return ToolResult.success(
            action="focus_ui_element", message="ok",
            state_confirmed=self.focus_confirmed, query_length=len(query), role=role,
        )


class FakeApps:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def open_app(self, app_name):
        self.calls.append(("open_app", app_name))
        if self.ok:
            return ToolResult.success(action="open_app", message="ok", target=app_name)
        return ToolResult.failure(action="open_app", message="ko", error_code="app_missing")


class FakeKeyboard:
    def __init__(self):
        self.calls = []

    def type_text(self, text):
        self.calls.append(("type_text", text))
        return ToolResult.success(
            action="type_text", message="ok", command_executed=True, state_confirmed=False,
        )

    def press_key(self, key):
        self.calls.append(("press_key", key))
        return ToolResult.success(
            action="press_key", message="ok", command_executed=True, state_confirmed=False,
        )


def make(windows=None, ui=None, apps=None, keyboard=None):
    return MessagingCapability(
        windows=windows or FakeWindows(),
        ui_accessibility=ui or FakeUI(),
        apps=apps or FakeApps(),
        keyboard=keyboard or FakeKeyboard(),
        sleeper=lambda _seconds: None,
    )


class VerifyRecipientTest(unittest.TestCase):
    def test_verified_when_header_names_recipient(self):
        result = make().verify_recipient("WhatsApp", "Joel")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["recipient_verified"])
        self.assertEqual(result.data["target_app"], "WhatsApp")

    def test_header_mismatch_refuses(self):
        ui = FakeUI(elements=[header("Alice Martin")])

        result = make(ui=ui).verify_recipient("WhatsApp", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "recipient_not_verified")
        self.assertEqual(result.data["reason"], "header_mismatch")

    def test_missing_header_refuses(self):
        ui = FakeUI(elements=[{"role": "AXStaticText", "title": "Discussions"}])

        result = make(ui=ui).verify_recipient("WhatsApp", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.data["reason"], "conversation_header_not_found")

    def test_name_in_message_bubble_never_verifies(self):
        # "Joel" appears only inside a message body, not in the header.
        ui = FakeUI(elements=[
            header("Alice Martin"),
            message_bubble("Votre message, Envoye a Joel, Lu"),
        ])

        result = make(ui=ui).verify_recipient("WhatsApp", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "recipient_not_verified")

    def test_refuses_when_app_not_active(self):
        windows = FakeWindows(active=ToolResult.success(
            action="get_active_window", message="ok", target_app="Safari",
        ))

        result = make(windows=windows).verify_recipient("WhatsApp", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.data["reason"], "active_app_mismatch")

    def test_propagates_window_read_failure(self):
        windows = FakeWindows(active=ToolResult.failure(
            action="get_active_window", message="echec", error_code="no_window",
        ))

        result = make(windows=windows).verify_recipient("WhatsApp", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "no_window")

    def test_short_recipient_is_rejected(self):
        result = make().verify_recipient("WhatsApp", "K")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_recipient")

    def test_full_name_matches_header(self):
        result = make().verify_recipient("WhatsApp", "Joel Chinda")

        self.assertTrue(result.ok)


class ComposerQueryTest(unittest.TestCase):
    def test_known_app_returns_composer_identifier(self):
        capability = make()

        self.assertEqual(
            capability.composer_query("WhatsApp"), "ChatBar_ComposerTextView"
        )
        self.assertEqual(
            capability.composer_query("whatsapp"), "ChatBar_ComposerTextView"
        )

    def test_unknown_app_returns_none(self):
        self.assertIsNone(make().composer_query("Claude"))
        self.assertIsNone(make().composer_query(None))

    def test_composer_queries_are_overridable(self):
        capability = MessagingCapability(
            windows=FakeWindows(),
            ui_accessibility=FakeUI(),
            composer_queries={"signal": "Signal_Composer"},
        )

        self.assertEqual(capability.composer_query("Signal"), "Signal_Composer")
        self.assertIsNone(capability.composer_query("WhatsApp"))


class SendTextTest(unittest.TestCase):
    def test_focuses_types_then_presses_send_and_confirms_emptied(self):
        ui = FakeUI(send_button_present=True, composer_value_after="")
        keyboard = FakeKeyboard()
        result = make(ui=ui, keyboard=keyboard).send_text("WhatsApp", "Salut")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])  # composer emptied
        # Clear, focus the composer by press, (type), press send, verify empty.
        self.assertEqual(ui.calls[0], ("set_value", "ChatBar_ComposerTextView", ""))
        self.assertEqual(ui.calls[1], ("activate_ui_element", "ChatBar_ComposerTextView"))
        self.assertEqual(ui.calls[2], ("activate_ui_element", "ChatBar_SendButton"))
        self.assertEqual(ui.calls[3], ("read_value", "ChatBar_ComposerTextView"))
        self.assertEqual(keyboard.calls, [("type_text", "Salut")])  # real keystrokes

    def test_missing_send_button_means_text_did_not_register_and_sends_nothing(self):
        ui = FakeUI(send_button_present=False)
        keyboard = FakeKeyboard()
        result = make(ui=ui, keyboard=keyboard).send_text("WhatsApp", "Salut")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "composer_not_filled")
        self.assertNotIn("read_value", [call[0] for call in ui.calls])  # never got to verify

    def test_not_emptied_after_send_is_command_executed_but_unconfirmed(self):
        ui = FakeUI(send_button_present=True, composer_value_after="Salut")
        result = make(ui=ui).send_text("WhatsApp", "Salut")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertFalse(result.data["state_confirmed"])

    def test_unsupported_app_refuses(self):
        result = make().send_text("Claude", "Salut")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "composer_unsupported")

    def test_empty_text_refused(self):
        result = make().send_text("WhatsApp", "   ")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_text")


class SequencedWindows:
    """Windows whose active app and focus confirmation follow fixed sequences,
    to simulate an app that is not frontmost at first then settles."""

    def __init__(self, active_apps, focus_confirms):
        self._active_apps = list(active_apps)
        self._focus_confirms = list(focus_confirms)
        self.calls = []

    def get_active_window(self):
        app = self._active_apps.pop(0) if self._active_apps else "WhatsApp"
        return ToolResult.success(
            action="get_active_window", message="ok", target_app=app,
        )

    def focus_window(self, app_name):
        self.calls.append(("focus_window", app_name))
        confirmed = self._focus_confirms.pop(0) if self._focus_confirms else True
        return ToolResult.success(
            action="focus_window", message="ok",
            state_confirmed=confirmed, target_app=app_name,
        )


class EnsureRecipientRetryTest(unittest.TestCase):
    def test_transient_not_frontmost_then_succeeds(self):
        # 1st verify: WhatsApp not active (Finder) -> navigable mismatch.
        # 1st navigate: focus_window not confirmed -> fails (no_window).
        # 2nd navigate: focus confirmed; re-verify sees WhatsApp + right header.
        windows = SequencedWindows(
            active_apps=["Finder", "WhatsApp"],
            focus_confirms=[False, True],
        )
        ui = FakeUI(elements=[header("Marie Curie")])
        capability = MessagingCapability(
            windows=windows,
            ui_accessibility=ui,
            apps=FakeApps(),
            keyboard=FakeKeyboard(),
            sleeper=lambda _seconds: None,
        )

        result = capability.ensure_recipient("WhatsApp", "Marie")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["recipient_verified"])
        self.assertEqual(len(windows.calls), 2)  # retried focus_window once

    def test_gives_up_after_attempts_and_fails_safe(self):
        windows = SequencedWindows(
            active_apps=["Finder", "Finder", "Finder", "Finder"],
            focus_confirms=[False, False, False],
        )
        ui = FakeUI(elements=[header("Marie Curie")])
        capability = MessagingCapability(
            windows=windows,
            ui_accessibility=ui,
            apps=FakeApps(),
            keyboard=FakeKeyboard(),
            navigate_attempts=3,
            sleeper=lambda _seconds: None,
        )

        result = capability.ensure_recipient("WhatsApp", "Marie")

        self.assertFalse(result.ok)  # never confirmed -> safe refusal
        self.assertEqual(len(windows.calls), 3)  # tried the configured attempts


class EnsureRecipientTest(unittest.TestCase):
    def test_already_open_match_does_not_navigate(self):
        ui = FakeUI(elements=[header("Joel Chinda")])
        apps = FakeApps()
        keyboard = FakeKeyboard()
        capability = make(ui=ui, apps=apps, keyboard=keyboard)

        result = capability.ensure_recipient("WhatsApp", "Joel")

        self.assertTrue(result.ok)
        self.assertEqual(apps.calls, [])      # no navigation
        self.assertEqual(keyboard.calls, [])

    def test_navigates_then_verifies(self):
        # First inspection = wrong chat, second (after navigation) = right chat.
        ui = FakeUI(inspects=[
            ToolResult.success(action="inspect_ui", message="ok",
                               elements=[header("Alice Martin")], truncated=False),
            ToolResult.success(action="inspect_ui", message="ok",
                               elements=[header("Joel Chinda")], truncated=False),
        ])
        apps = FakeApps()
        keyboard = FakeKeyboard()
        capability = make(ui=ui, apps=apps, keyboard=keyboard)

        result = capability.ensure_recipient("WhatsApp", "Joel")

        self.assertTrue(result.ok)
        self.assertEqual(apps.calls, [("open_app", "WhatsApp")])
        self.assertIn(("focus_ui_element", "TokenizedSearchBar_TextView", None), ui.calls)
        self.assertEqual(keyboard.calls, [("type_text", "Joel"), ("press_key", "enter")])

    def test_navigation_that_still_mismatches_refuses(self):
        ui = FakeUI(inspects=[
            ToolResult.success(action="inspect_ui", message="ok",
                               elements=[header("Alice Martin")], truncated=False),
            ToolResult.success(action="inspect_ui", message="ok",
                               elements=[header("Bob Dupont")], truncated=False),
        ])
        keyboard = FakeKeyboard()
        capability = make(ui=ui, keyboard=keyboard)

        result = capability.ensure_recipient("WhatsApp", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "recipient_not_verified")
        self.assertEqual(keyboard.calls, [("type_text", "Joel"), ("press_key", "enter")])

    def test_unsupported_app_does_not_navigate(self):
        ui = FakeUI(elements=[header("Alice")])
        apps = FakeApps()
        keyboard = FakeKeyboard()
        capability = make(ui=ui, apps=apps, keyboard=keyboard)

        result = capability.ensure_recipient("Signal", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(apps.calls, [])  # no search support -> no navigation
        self.assertEqual(keyboard.calls, [])


class NavigateToRecipientTest(unittest.TestCase):
    def test_happy_path_sequence(self):
        apps = FakeApps()
        windows = FakeWindows()
        ui = FakeUI()
        keyboard = FakeKeyboard()
        capability = make(windows=windows, ui=ui, apps=apps, keyboard=keyboard)

        result = capability.navigate_to_recipient("WhatsApp", "Joel")

        self.assertTrue(result.ok)
        self.assertEqual(apps.calls, [("open_app", "WhatsApp")])
        self.assertEqual(windows.calls, [("focus_window", "WhatsApp")])
        self.assertEqual(ui.calls, [("focus_ui_element", "TokenizedSearchBar_TextView", None)])
        self.assertEqual(keyboard.calls, [("type_text", "Joel"), ("press_key", "enter")])

    def test_unsupported_app(self):
        result = make().navigate_to_recipient("Signal", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "search_not_supported")

    def test_focus_window_failure_stops(self):
        windows = FakeWindows(focus_confirmed=False)
        keyboard = FakeKeyboard()
        capability = make(windows=windows, keyboard=keyboard)

        result = capability.navigate_to_recipient("WhatsApp", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "no_window")
        self.assertEqual(keyboard.calls, [])  # never typed

    def test_search_field_not_focusable_stops(self):
        ui = FakeUI(focus_confirmed=False)
        keyboard = FakeKeyboard()
        capability = make(ui=ui, keyboard=keyboard)

        result = capability.navigate_to_recipient("WhatsApp", "Joel")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "search_field_not_found")
        self.assertEqual(keyboard.calls, [])


if __name__ == "__main__":
    unittest.main()
