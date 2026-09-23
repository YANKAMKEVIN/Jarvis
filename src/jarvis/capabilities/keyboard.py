from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.keyboard import KeyboardError, KeyboardTools


class KeyboardCapability:
    def __init__(
        self,
        security=None,
        keyboard_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.keyboard_tools = (
            keyboard_tools
            if keyboard_tools is not None
            else KeyboardTools()
        )

    def type_text(self, text: str) -> ToolResult:
        try:
            validated = self.keyboard_tools.validate_type_text(text)
        except KeyboardError as error:
            return self._keyboard_failure("type_text", error)

        security_result = self._security_result(
            "type_text",
            f"length:{validated['length']}",
        )

        if security_result is not None:
            return security_result

        try:
            state = self.keyboard_tools.type_text(text)
        except KeyboardError as error:
            return self._keyboard_failure("type_text", error)
        except Exception as error:
            return self._system_error_result("type_text", error)

        return ToolResult.success(
            action="type_text",
            message=(
                "La commande de saisie a ete envoyee, mais Jarvis ne peut "
                "pas confirmer que le texte a ete applique."
            ),
            **state,
        )

    def press_key(self, key: str) -> ToolResult:
        try:
            normalized_key = self.keyboard_tools.validate_key(key)
        except KeyboardError as error:
            return self._keyboard_failure("press_key", error)

        security_result = self._security_result("press_key", normalized_key)

        if security_result is not None:
            return security_result

        try:
            state = self.keyboard_tools.press_key(normalized_key)
        except KeyboardError as error:
            return self._keyboard_failure("press_key", error)
        except Exception as error:
            return self._system_error_result("press_key", error)

        return ToolResult.success(
            action="press_key",
            message=(
                "La touche a ete envoyee, mais Jarvis ne peut pas confirmer "
                "son effet dans l'application active."
            ),
            **state,
        )

    def hotkey(self, keys: list[str]) -> ToolResult:
        try:
            normalized_hotkey = self.keyboard_tools.validate_hotkey(keys)
        except KeyboardError as error:
            return self._keyboard_failure("hotkey", error)

        security_result = self._security_result(
            "hotkey",
            "+".join(normalized_hotkey),
        )

        if security_result is not None:
            return security_result

        try:
            state = self.keyboard_tools.hotkey(list(normalized_hotkey))
        except KeyboardError as error:
            return self._keyboard_failure("hotkey", error)
        except Exception as error:
            return self._system_error_result("hotkey", error)

        return ToolResult.success(
            action="hotkey",
            message=(
                "Le raccourci clavier a ete envoye, mais Jarvis ne peut pas "
                "confirmer son effet dans l'application active."
            ),
            **state,
        )

    def _security_result(self, action: str, target: str | None) -> ToolResult | None:
        decision = self.security.evaluate(create_intent(action, target))

        if not decision.allowed:
            return ToolResult.failure(
                action=action,
                message="Jarvis n'est pas autorise a envoyer cette action clavier.",
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
    def _keyboard_failure(action: str, error: KeyboardError) -> ToolResult:
        return ToolResult(
            ok=False,
            action=action,
            message=error.message,
            data=error.data,
            error_code=error.code,
        )

    @staticmethod
    def _system_error_result(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=f"Echec de l'action clavier : {error}",
            error_code="system_error",
        )
