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
    "get_time": RiskLevel.SAFE,
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
