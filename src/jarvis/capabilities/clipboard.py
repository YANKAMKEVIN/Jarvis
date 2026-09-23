from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.clipboard import ClipboardError, ClipboardTools


class ClipboardCapability:
    def __init__(
        self,
        security=None,
        clipboard_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.clipboard_tools = (
            clipboard_tools
            if clipboard_tools is not None
            else ClipboardTools()
        )

    def get_clipboard_text(self) -> ToolResult:
        try:
            state = self.clipboard_tools.get_text()
        except ClipboardError as error:
            return self._clipboard_failure("get_clipboard_text", error)
        except Exception as error:
            return self._system_error_result("get_clipboard_text", error)

        if state.get("has_text"):
            if state.get("truncated"):
                message = (
                    "Le presse-papiers contient du texte, mais seul le debut "
                    "a ete retourne car il est trop long."
                )
            else:
                message = "Le presse-papiers contient du texte."
        else:
            message = "Le presse-papiers ne contient pas de texte lisible."

        return ToolResult.success(
            action="get_clipboard_text",
            message=message,
            **state,
        )

    def set_clipboard_text(self, text: str) -> ToolResult:
        security_result = self._security_result("set_clipboard_text")

        if security_result is not None:
            return security_result

        try:
            state = self.clipboard_tools.set_text(text)
        except ClipboardError as error:
            return self._clipboard_failure("set_clipboard_text", error)
        except Exception as error:
            return self._system_error_result("set_clipboard_text", error)

        if state.get("state_confirmed"):
            message = "Le texte a ete copie dans le presse-papiers et verifie."
        else:
            message = (
                "La commande de copie a ete executee, mais Jarvis n'a pas pu "
                "confirmer le contenu final du presse-papiers."
            )

        return ToolResult.success(
            action="set_clipboard_text",
            message=message,
            **state,
        )

    def clear_clipboard(self) -> ToolResult:
        security_result = self._security_result("clear_clipboard")

        if security_result is not None:
            return security_result

        try:
            state = self.clipboard_tools.clear()
        except ClipboardError as error:
            return self._clipboard_failure("clear_clipboard", error)
        except Exception as error:
            return self._system_error_result("clear_clipboard", error)

        if state.get("state_confirmed"):
            message = "Le presse-papiers ne contient plus de texte lisible."
        else:
            message = (
                "La commande d'effacement a ete executee, mais Jarvis n'a "
                "pas pu confirmer l'etat final du presse-papiers."
            )

        return ToolResult.success(
            action="clear_clipboard",
            message=message,
            **state,
        )

    def _security_result(self, action: str) -> ToolResult | None:
        decision = self.security.evaluate(create_intent(action))

        if not decision.allowed:
            return ToolResult.failure(
                action=action,
                message="Jarvis n'est pas autorise a modifier le presse-papiers.",
                error_code="security_denied",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return ToolResult.failure(
                action=action,
                message=(
                    "Cette action necessite une confirmation non disponible "
                    "en mode Live."
                ),
                error_code="confirmation_required",
                requires_confirmation=True,
                reason=decision.reason,
            )

        return None

    @staticmethod
    def _clipboard_failure(action: str, error: ClipboardError) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=error.message,
            error_code=error.code,
        )

    @staticmethod
    def _system_error_result(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=f"Echec de l'operation presse-papiers : {error}",
            error_code="system_error",
        )
