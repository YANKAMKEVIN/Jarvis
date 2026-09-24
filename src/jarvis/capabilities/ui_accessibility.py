from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.accessibility import AccessibilityError, AccessibilityTools


class UIAccessibilityCapability:
    def __init__(
        self,
        security=None,
        accessibility_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.accessibility_tools = (
            accessibility_tools
            if accessibility_tools is not None
            else AccessibilityTools()
        )

    def inspect_ui(self, max_depth: int = 4, max_elements: int = 80) -> ToolResult:
        try:
            state = self.accessibility_tools.inspect_ui(max_depth, max_elements)
        except AccessibilityError as error:
            return self._accessibility_failure("inspect_ui", error)
        except Exception as error:
            return self._system_error_result("inspect_ui", error)

        return ToolResult.success(
            action="inspect_ui",
            message=(
                f"{state['count']} element(s) Accessibility exploitable(s) "
                "ont ete trouves dans la fenetre actuelle."
            ),
            **state,
        )

    def find_ui_elements(self, query: str, role: str | None = None) -> ToolResult:
        try:
            state = self.accessibility_tools.find_ui_elements(query, role)
        except AccessibilityError as error:
            return self._accessibility_failure("find_ui_elements", error)
        except Exception as error:
            return self._system_error_result("find_ui_elements", error)

        count = state["candidate_count"]

        if count > 1:
            return ToolResult(
                ok=False,
                action="find_ui_elements",
                message=(
                    "Plusieurs elements Accessibility correspondent a cette "
                    "recherche."
                ),
                data=state,
                error_code="ambiguous_ui_element",
            )

        return ToolResult.success(
            action="find_ui_elements",
            message="Un element Accessibility correspond a cette recherche.",
            **state,
        )

    def focus_ui_element(self, query: str, role: str | None = None) -> ToolResult:
        security_result = self._security_result("focus_ui_element", self._target(query, role))

        if security_result is not None:
            return security_result

        try:
            state = self.accessibility_tools.focus_ui_element(query, role)
        except AccessibilityError as error:
            return self._accessibility_failure("focus_ui_element", error)
        except Exception as error:
            return self._system_error_result("focus_ui_element", error)

        if state.get("state_confirmed"):
            message = "Le focus Accessibility a ete confirme sur cet element."
        else:
            message = (
                "La commande de focus Accessibility a ete envoyee, mais "
                "Jarvis n'a pas pu confirmer l'etat final."
            )

        return ToolResult.success(
            action="focus_ui_element",
            message=message,
            **state,
        )

    def activate_ui_element(self, query: str, role: str | None = None) -> ToolResult:
        security_result = self._security_result(
            "activate_ui_element",
            self._target(query, role),
        )

        if security_result is not None:
            return security_result

        try:
            state = self.accessibility_tools.activate_ui_element(query, role)
        except AccessibilityError as error:
            return self._accessibility_failure("activate_ui_element", error)
        except Exception as error:
            return self._system_error_result("activate_ui_element", error)

        if state.get("state_confirmed"):
            message = "L'action Accessibility a ete envoyee et un etat AX observable l'a confirmee."
        else:
            message = (
                "La commande Accessibility a ete envoyee, mais Jarvis ne peut "
                "pas confirmer son effet applicatif."
            )

        return ToolResult.success(
            action="activate_ui_element",
            message=message,
            **state,
        )

    @staticmethod
    def _target(query: str, role: str | None) -> str:
        return f"{role or 'any'}:{len(query) if isinstance(query, str) else 0}"

    def _security_result(self, action: str, target: str | None) -> ToolResult | None:
        decision = self.security.evaluate(create_intent(action, target))

        if not decision.allowed:
            return ToolResult.failure(
                action=action,
                message="Jarvis n'est pas autorise a agir sur cet element UI.",
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
    def _accessibility_failure(action: str, error: AccessibilityError) -> ToolResult:
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
            message=f"Echec Accessibility : {error}",
            error_code="system_error",
        )
