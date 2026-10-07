from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    SAFE = "safe"
    CONFIRM = "confirm"
    DANGEROUS = "dangerous"


@dataclass
class Intent:
    action: str
    target: str | None = None
    risk: RiskLevel = RiskLevel.SAFE


ALLOWED_ACTIONS = {
    "open_app": RiskLevel.SAFE,
    "close_app": RiskLevel.SAFE,
    "open_url": RiskLevel.SAFE,
    "web_search": RiskLevel.SAFE,
    "get_time": RiskLevel.SAFE,
    "get_date": RiskLevel.SAFE,
    "set_volume": RiskLevel.SAFE,
    "mute": RiskLevel.SAFE,
    "unmute": RiskLevel.SAFE,
    "play_pause": RiskLevel.SAFE,
    "next_track": RiskLevel.SAFE,
    "previous_track": RiskLevel.SAFE,
    "set_brightness": RiskLevel.SAFE,
    "lock_screen": RiskLevel.SAFE,
    "focus_window": RiskLevel.SAFE,
    "minimize_window": RiskLevel.SAFE,
    "maximize_window": RiskLevel.SAFE,
    "move_window": RiskLevel.SAFE,
    "open_file": RiskLevel.SAFE,
    "open_folder": RiskLevel.SAFE,
    "create_folder": RiskLevel.SAFE,
    "rename_file": RiskLevel.SAFE,
    "move_file": RiskLevel.SAFE,
    "set_clipboard_text": RiskLevel.SAFE,
    "clear_clipboard": RiskLevel.SAFE,
    "type_text": RiskLevel.SAFE,
    "press_key": RiskLevel.SAFE,
    "hotkey": RiskLevel.SAFE,
    # Deleting the current selection is mutating but text-level and reversible
    # via Undo in most apps. It is SAFE like type_text (also a mutating edit):
    # CONFIRM has no usable confirmation channel in Live, and the safety comes
    # from the controlled composite (verified editable target, stop-on-failure,
    # single Backspace), not from a gate that would block the action entirely.
    "delete_selection": RiskLevel.SAFE,
    "move_mouse": RiskLevel.SAFE,
    "click": RiskLevel.SAFE,
    "double_click": RiskLevel.SAFE,
    "right_click": RiskLevel.SAFE,
    "scroll": RiskLevel.SAFE,
    "focus_ui_element": RiskLevel.SAFE,
    # V1 allows the primitive AXPress action for test and assisted use. This
    # does not mean every business consequence of a pressed UI button is safe.
    "activate_ui_element": RiskLevel.SAFE,
    "conversation": RiskLevel.SAFE,
}


def create_intent(action: str, target: str | None = None) -> Intent:
    if action not in ALLOWED_ACTIONS:
        return Intent(
            action=action,
            target=target,
            risk=RiskLevel.DANGEROUS,
        )

    return Intent(
        action=action,
        target=target,
        risk=ALLOWED_ACTIONS[action],
    )
