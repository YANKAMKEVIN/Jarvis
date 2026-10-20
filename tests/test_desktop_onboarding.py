import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from jarvis.desktop import onboarding
from jarvis.desktop.onboarding import (
    ONBOARDING_VERSION, PERMISSIONS, mark_done, needs_onboarding,
    permission_items,
)


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


# --- pure logic (no Qt) -----------------------------------------------------


def test_first_run_needs_onboarding_then_marked_done():
    settings = FakeSettings()
    assert needs_onboarding(settings) is True
    mark_done(settings)
    assert needs_onboarding(settings) is False


def test_old_version_triggers_onboarding_again():
    settings = FakeSettings({"onboarding/version": ONBOARDING_VERSION - 1})
    assert needs_onboarding(settings) is True


def test_permission_items_tristate_status():
    rows = permission_items({
        "calendar": True, "screen_recording": False, "microphone": None,
    })
    assert len(rows) == len(PERMISSIONS)
    by_key = {row["key"]: row for row in rows}
    assert by_key["calendar"]["status_text"] == "accordé"
    assert by_key["screen_recording"]["status_text"] == "à autoriser"
    # Unknown (absent or None) reads as asked at first use.
    assert by_key["microphone"]["status_text"] == "au premier usage"
    assert by_key["automation"]["status_text"] == "au premier usage"


def test_every_permission_has_a_settings_url():
    for spec in PERMISSIONS:
        assert spec.settings_url.endswith(spec.pane)
        assert "Privacy_" in spec.settings_url


# --- Qt dialog (offscreen) --------------------------------------------------


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_dialog_lists_every_permission(app):
    settings = FakeSettings()
    dialog = onboarding.make_onboarding_dialog(
        settings, snapshot={}, request=lambda key: None, open_settings_fn=lambda url: None,
    )
    assert set(dialog.rows) == {spec.key for spec in PERMISSIONS}


def test_request_button_calls_injected_request_with_key(app):
    calls = []
    settings = FakeSettings()
    dialog = onboarding.make_onboarding_dialog(
        settings,
        snapshot={"calendar": False},
        request=lambda key: calls.append(key),
        open_settings_fn=lambda url: None,
    )
    dialog.rows["calendar"]["request"].click()
    assert calls == ["calendar"]


def test_non_requestable_row_opens_settings(app):
    opened = []
    settings = FakeSettings()
    dialog = onboarding.make_onboarding_dialog(
        settings,
        snapshot={"automation": False},
        request=lambda key: (_ for _ in ()).throw(AssertionError("should not request")),
        open_settings_fn=lambda url: opened.append(url),
    )
    # Automation is not requestable: its primary button opens Settings.
    dialog.rows["automation"]["request"].click()
    assert opened and "Privacy_Automation" in opened[0]


def test_granted_permission_has_no_request_button(app):
    settings = FakeSettings()
    dialog = onboarding.make_onboarding_dialog(
        settings, snapshot={"calendar": True},
        request=lambda key: None, open_settings_fn=lambda url: None,
    )
    assert dialog.rows["calendar"]["request"] is None


def test_finish_marks_done_and_closes(app):
    settings = FakeSettings()
    dialog = onboarding.make_onboarding_dialog(
        settings, snapshot={}, request=lambda key: None, open_settings_fn=lambda url: None,
    )
    dialog.finish_button.click()
    assert needs_onboarding(settings) is False
    assert not dialog.isVisible()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
