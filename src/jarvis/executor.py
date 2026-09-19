from dataclasses import dataclass

from jarvis.brain import Brain
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.macos import MacOSTools


@dataclass
class ExecutionResult:
    message: str
    needs_confirmation: bool = False
    intent: object | None = None


class CommandExecutor:
    def __init__(self):
        self.brain = Brain()
        self.security = SecurityManager()
        self.tools = MacOSTools()

    def execute(
        self,
        command: str,
        confirmed: bool = False,
    ) -> ExecutionResult:
        detected = self.brain.detect_intent(command)

        action = detected.get("action", "conversation")
        target = detected.get("target")

        if action == "conversation":
            answer = self.brain.think(command)
            return ExecutionResult(answer)

        intent = create_intent(action, target)
        decision = self.security.evaluate(intent)

        if not decision.allowed:
            return ExecutionResult(
                "Je ne suis pas autorisee a effectuer cette action."
            )

        if decision.requires_confirmation and not confirmed:
            return ExecutionResult(
                "Cette action necessite votre confirmation.",
                needs_confirmation=True,
                intent=intent,
            )

        if intent.action == "open_app":
            if not intent.target:
                return ExecutionResult(
                    "Quelle application dois-je ouvrir ?"
                )
            return ExecutionResult(
                self.tools.open_app(intent.target)
            )

        if intent.action == "close_app":
            if not intent.target:
                return ExecutionResult(
                    "Quelle application dois-je fermer ?"
                )
            return ExecutionResult(
                self.tools.close_app(intent.target)
            )

        if intent.action == "open_url":
            if not intent.target:
                return ExecutionResult(
                    "Quel site dois-je ouvrir ?"
                )
            return ExecutionResult(
                self.tools.open_url(intent.target)
            )

        if intent.action == "web_search":
            if not intent.target:
                return ExecutionResult(
                    "Que dois-je rechercher ?"
                )
            return ExecutionResult(
                self.tools.web_search(intent.target)
            )

        if intent.action == "get_date":
            date = self.tools.get_date()
            return ExecutionResult(
                f"Nous sommes le {date}."
            )

        if intent.action == "set_volume":
            if intent.target is None:
                return ExecutionResult(
                    "A quel niveau dois-je regler le volume ?"
                )

            try:
                level = int(intent.target)
            except (TypeError, ValueError):
                return ExecutionResult(
                    "Je n'ai pas compris le niveau du volume."
                )

            return ExecutionResult(
                self.tools.set_volume(level)
            )

        if intent.action == "mute":
            return ExecutionResult(
                self.tools.mute()
            )

        if intent.action == "unmute":
            return ExecutionResult(
                self.tools.unmute()
            )

        return ExecutionResult(
            "Cette action n'est pas encore disponible."
        )
