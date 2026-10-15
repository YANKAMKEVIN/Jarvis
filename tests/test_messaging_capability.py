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
    def __init__(self, active=None):
        self.active = active or ToolResult.success(
            action="get_active_window", message="ok", target_app="WhatsApp",
        )

    def get_active_window(self):
        return self.active


class FakeUI:
    def __init__(self, elements=None, inspect=None):
        if inspect is not None:
            self.inspect = inspect
        else:
            self.inspect = ToolResult.success(
                action="inspect_ui", message="ok",
                elements=elements if elements is not None else [header()],
                truncated=False,
            )
        self.calls = []

    def inspect_ui(self, max_depth=4, max_elements=80):
        self.calls.append((max_depth, max_elements))
        return self.inspect


def make(windows=None, ui=None):
    return MessagingCapability(windows=windows or FakeWindows(), ui_accessibility=ui or FakeUI())


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


if __name__ == "__main__":
    unittest.main()
