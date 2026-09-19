from dataclasses import dataclass

from jarvis.intents import Intent, RiskLevel


@dataclass
class SecurityDecision:
    allowed: bool
    requires_confirmation: bool
    reason: str


class SecurityManager:
    def evaluate(self, intent: Intent) -> SecurityDecision:

        if intent.risk == RiskLevel.SAFE:
            return SecurityDecision(
                allowed=True,
                requires_confirmation=False,
                reason="Action autorisee.",
            )

        if intent.risk == RiskLevel.CONFIRM:
            return SecurityDecision(
                allowed=True,
                requires_confirmation=True,
                reason="Confirmation utilisateur requise.",
            )

        return SecurityDecision(
            allowed=False,
            requires_confirmation=False,
            reason="Action dangereuse ou inconnue bloquee.",
        )
