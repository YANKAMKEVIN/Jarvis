from dataclasses import dataclass, field
import os

from jarvis.brain import Brain
from jarvis.intents import create_intent
from jarvis.knowledge.models import SourceReference
from jarvis.knowledge.service import KnowledgeService
from jarvis.routing import RequestType
from jarvis.security import SecurityManager
from jarvis.tools.macos import MacOSTools


@dataclass
class ExecutionResult:
    message: str
    needs_confirmation: bool = False
    intent: object | None = None
    request_type: RequestType | None = None
    requires_external_knowledge: bool = False
    external_knowledge_retrieved: bool = False
    sources: list[SourceReference] = field(default_factory=list)


class CommandExecutor:
    def __init__(
        self,
        brain=None,
        security=None,
        tools=None,
        knowledge_service=None,
    ):
        self.brain = brain if brain is not None else Brain()
        self.security = (
            security
            if security is not None
            else SecurityManager()
        )
        self.tools = tools if tools is not None else MacOSTools()
        self.knowledge_service = (
            knowledge_service
            if knowledge_service is not None
            else KnowledgeService(self.brain)
        )

    def execute(
        self,
        command: str,
        confirmed: bool = False,
    ) -> ExecutionResult:
        route = self.brain.route_request(command)
        self._debug_routing(
            "route",
            text=command,
            request_type=route.request_type.value,
            reason=route.reason,
        )

        if route.request_type == RequestType.KNOWLEDGE:
            self._debug_routing(
                "knowledge",
                system_action_executed=False,
                fallback_to_llm=False,
            )
            answer = self.knowledge_service.answer(command)

            return ExecutionResult(
                answer.message,
                request_type=RequestType.KNOWLEDGE,
                requires_external_knowledge=answer.requires_external_knowledge,
                external_knowledge_retrieved=(
                    answer.external_knowledge_retrieved
                ),
                sources=answer.sources,
            )

        if route.request_type == RequestType.CONVERSATION:
            self._debug_routing(
                "conversation",
                system_action_executed=False,
                fallback_to_llm=True,
            )
            answer = self.brain.think(command)
            return ExecutionResult(
                answer,
                request_type=RequestType.CONVERSATION,
            )

        detected = self.brain.detect_intent(command)

        action = detected.get("action", "conversation")
        target = detected.get("target")
        self._debug_routing(
            "intent",
            action=action,
            target=target,
        )

        if action == "conversation":
            self._debug_routing(
                "action_fallback",
                system_action_executed=False,
                fallback_to_llm=True,
            )
            answer = self.brain.think(command)
            return ExecutionResult(
                answer,
                request_type=RequestType.CONVERSATION,
            )

        intent = create_intent(action, target)
        return self.execute_intent(intent, confirmed=confirmed)

    def execute_intent(self, intent, confirmed: bool = False) -> ExecutionResult:
        """Execute the exact previewed intent without asking the model again.

        Rebuild risk from the action registry: a caller cannot downgrade it by
        supplying a hand-crafted Intent. UI confirmations retain action/target.
        """
        intent = create_intent(intent.action, intent.target)
        decision = self.security.evaluate(intent)
        self._debug_routing(
            "security",
            action=intent.action,
            target=intent.target,
            allowed=decision.allowed,
            requires_confirmation=decision.requires_confirmation,
        )

        if not decision.allowed:
            self._debug_routing(
                "blocked",
                system_action_executed=False,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                "Je ne suis pas autorisee a effectuer cette action.",
                request_type=RequestType.ACTION,
                intent=intent,
            )

        if decision.requires_confirmation and not confirmed:
            self._debug_routing(
                "confirmation_required",
                system_action_executed=False,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                "Cette action necessite votre confirmation.",
                needs_confirmation=True,
                intent=intent,
                request_type=RequestType.ACTION,
            )

        if intent.action == "open_app":
            if not intent.target:
                self._debug_routing(
                    "missing_parameter",
                    action=intent.action,
                    system_action_executed=False,
                    fallback_to_llm=False,
                )
                return ExecutionResult(
                    "Quelle application dois-je ouvrir ?",
                    request_type=RequestType.ACTION,
                    intent=intent,
                )
            self._debug_routing(
                "execute_system_action",
                action=intent.action,
                target=intent.target,
                system_action_executed=True,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                self.tools.open_app(intent.target),
                request_type=RequestType.ACTION,
                intent=intent,
            )

        if intent.action == "close_app":
            if not intent.target:
                self._debug_routing(
                    "missing_parameter",
                    action=intent.action,
                    system_action_executed=False,
                    fallback_to_llm=False,
                )
                return ExecutionResult(
                    "Quelle application dois-je fermer ?",
                    request_type=RequestType.ACTION,
                    intent=intent,
                )
            self._debug_routing(
                "execute_system_action",
                action=intent.action,
                target=intent.target,
                system_action_executed=True,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                self.tools.close_app(intent.target),
                request_type=RequestType.ACTION,
                intent=intent,
            )

        if intent.action == "open_url":
            if not intent.target:
                self._debug_routing(
                    "missing_parameter",
                    action=intent.action,
                    system_action_executed=False,
                    fallback_to_llm=False,
                )
                return ExecutionResult(
                    "Quel site dois-je ouvrir ?",
                    request_type=RequestType.ACTION,
                    intent=intent,
                )
            self._debug_routing(
                "execute_system_action",
                action=intent.action,
                target=intent.target,
                system_action_executed=True,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                self.tools.open_url(intent.target),
                request_type=RequestType.ACTION,
                intent=intent,
            )

        if intent.action == "web_search":
            if not intent.target:
                self._debug_routing(
                    "missing_parameter",
                    action=intent.action,
                    system_action_executed=False,
                    fallback_to_llm=False,
                )
                return ExecutionResult(
                    "Que dois-je rechercher ?",
                    request_type=RequestType.ACTION,
                    intent=intent,
                )
            self._debug_routing(
                "execute_system_action",
                action=intent.action,
                target=intent.target,
                system_action_executed=True,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                self.tools.web_search(intent.target),
                request_type=RequestType.ACTION,
                intent=intent,
            )

        if intent.action == "get_date":
            self._debug_routing(
                "execute_system_action",
                action=intent.action,
                system_action_executed=True,
                fallback_to_llm=False,
            )
            date = self.tools.get_date()
            return ExecutionResult(
                f"Nous sommes le {date}.",
                request_type=RequestType.ACTION,
                intent=intent,
            )

        if intent.action == "set_volume":
            if intent.target is None:
                self._debug_routing(
                    "missing_parameter",
                    action=intent.action,
                    system_action_executed=False,
                    fallback_to_llm=False,
                )
                return ExecutionResult(
                    "A quel niveau dois-je regler le volume ?",
                    request_type=RequestType.ACTION,
                    intent=intent,
                )

            try:
                level = int(intent.target)
            except (TypeError, ValueError):
                self._debug_routing(
                    "invalid_parameter",
                    action=intent.action,
                    target=intent.target,
                    system_action_executed=False,
                    fallback_to_llm=False,
                )
                return ExecutionResult(
                    "Je n'ai pas compris le niveau du volume.",
                    request_type=RequestType.ACTION,
                    intent=intent,
                )

            self._debug_routing(
                "execute_system_action",
                action=intent.action,
                target=level,
                system_action_executed=True,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                self.tools.set_volume(level),
                request_type=RequestType.ACTION,
                intent=intent,
            )

        if intent.action == "mute":
            self._debug_routing(
                "execute_system_action",
                action=intent.action,
                system_action_executed=True,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                self.tools.mute(),
                request_type=RequestType.ACTION,
                intent=intent,
            )

        if intent.action == "unmute":
            self._debug_routing(
                "execute_system_action",
                action=intent.action,
                system_action_executed=True,
                fallback_to_llm=False,
            )
            return ExecutionResult(
                self.tools.unmute(),
                request_type=RequestType.ACTION,
                intent=intent,
            )

        self._debug_routing(
            "unavailable_action",
            action=intent.action,
            target=intent.target,
            system_action_executed=False,
            fallback_to_llm=False,
        )
        return ExecutionResult(
            "Cette action n'est pas encore disponible.",
            request_type=RequestType.ACTION,
            intent=intent,
        )

    @staticmethod
    def _debug_routing(event: str, **fields) -> None:
        if os.environ.get("JARVIS_DEBUG_ROUTING") != "1":
            return

        print("============== JARVIS ROUTING DEBUG ==============")
        print(f"EVENT: {event}")

        for key, value in fields.items():
            print(f"{key}: {value}")

        print("==================================================")

