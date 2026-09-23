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
