from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.mouse import MouseError, MouseTools


class MouseCapability:
    def __init__(
        self,
        security=None,
        mouse_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.mouse_tools = mouse_tools if mouse_tools is not None else MouseTools()

    def get_mouse_position(self) -> ToolResult:
        try:
            state = self.mouse_tools.get_position()
        except MouseError as error:
            return self._mouse_failure("get_mouse_position", error)
        except Exception as error:
            return self._system_error_result("get_mouse_position", error)

        return ToolResult.success(
            action="get_mouse_position",
            message=f"La souris est en position x={state['x']}, y={state['y']}.",
            **state,
        )

    def move_mouse(self, x: int, y: int) -> ToolResult:
        try:
            target_x, target_y = self.mouse_tools.validate_coordinates(x, y)
        except MouseError as error:
            return self._mouse_failure("move_mouse", error)

        security_result = self._security_result(
            "move_mouse",
            f"{target_x},{target_y}",
        )

        if security_result is not None:
            return security_result

        try:
            state = self.mouse_tools.move(target_x, target_y)
        except MouseError as error:
            return self._mouse_failure("move_mouse", error)
        except Exception as error:
            return self._system_error_result("move_mouse", error)

        if state.get("state_confirmed"):
            message = "Le pointeur a ete deplace a la position demandee."
        else:
            message = (
                "La commande de deplacement souris a ete envoyee, mais "
                "Jarvis n'a pas pu confirmer la position finale."
            )

        return ToolResult.success(
            action="move_mouse",
            message=message,
            **state,
        )

    def click(self) -> ToolResult:
        return self._click_action("click", self.mouse_tools.click)

    def double_click(self) -> ToolResult:
        return self._click_action("double_click", self.mouse_tools.double_click)

    def right_click(self) -> ToolResult:
        return self._click_action("right_click", self.mouse_tools.right_click)

    def scroll(self, direction: str, amount: int = 3) -> ToolResult:
        try:
            normalized_direction = self.mouse_tools.validate_scroll_direction(direction)
            normalized_amount = self.mouse_tools.validate_scroll_amount(amount)
        except MouseError as error:
            return self._mouse_failure("scroll", error)

        security_result = self._security_result(
            "scroll",
            f"{normalized_direction}:{normalized_amount}",
        )

        if security_result is not None:
            return security_result

        try:
            state = self.mouse_tools.scroll(normalized_direction, normalized_amount)
        except MouseError as error:
            return self._mouse_failure("scroll", error)
        except Exception as error:
            return self._system_error_result("scroll", error)

        return ToolResult.success(
            action="scroll",
            message=(
                "La commande de scroll a ete envoyee, mais Jarvis ne peut "
                "pas confirmer son effet dans l'application active."
            ),
            **state,
        )

    def _click_action(self, action: str, callback) -> ToolResult:
        security_result = self._security_result(action, "current_pointer")

        if security_result is not None:
            return security_result

        try:
            state = callback()
        except MouseError as error:
            return self._mouse_failure(action, error)
        except Exception as error:
            return self._system_error_result(action, error)

        return ToolResult.success(
            action=action,
            message=(
                "La commande de clic a ete envoyee, mais Jarvis ne peut "
                "pas confirmer son effet dans l'application active."
            ),
            **state,
        )

    def _security_result(self, action: str, target: str | None) -> ToolResult | None:
        decision = self.security.evaluate(create_intent(action, target))

        if not decision.allowed:
            return ToolResult.failure(
                action=action,
                message="Jarvis n'est pas autorise a envoyer cette action souris.",
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
    def _mouse_failure(action: str, error: MouseError) -> ToolResult:
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
            message=f"Echec de l'action souris : {error}",
            error_code="system_error",
        )
