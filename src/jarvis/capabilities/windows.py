from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.macos import MacOSTools


class WindowCapability:
    VALID_POSITIONS = {"left", "right", "center", "fullscreen"}

    def __init__(
        self,
        security=None,
        macos_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.macos_tools = macos_tools if macos_tools is not None else MacOSTools()

    def get_active_window(self) -> ToolResult:
        try:
            state = self.macos_tools.get_active_window()
        except Exception as error:
            return self._window_error_result("get_active_window", error)

        target_app = state.get("target_app") or "l'application active"
        title = state.get("window_title")

        if title:
            message = f"La fenetre active est {title} dans {target_app}."
        else:
            message = f"La fenetre active appartient a {target_app}."

        return ToolResult.success(
            action="get_active_window",
            message=message,
            **state,
        )

    def focus_window(self, app_name: str) -> ToolResult:
        valid_name = self._validate_app_name(app_name)

        if valid_name is None:
            return self._invalid_app_name_result("focus_window")

        decision = self.security.evaluate(
            create_intent("focus_window", valid_name),
        )
        security_result = self._security_result_if_blocked("focus_window", decision)

        if security_result is not None:
            return security_result

        try:
            state = self.macos_tools.focus_window(valid_name)
        except Exception as error:
            return self._window_error_result("focus_window", error)

        if state.get("state_confirmed"):
            message = f"{valid_name} est maintenant au premier plan."
        else:
            message = (
                "La commande de focus a ete envoyee, mais Jarvis n'a pas pu "
                "confirmer que la fenetre est au premier plan."
            )

        return ToolResult.success(
            action="focus_window",
            message=message,
            **state,
        )

    def minimize_window(self, app_name: str | None = None) -> ToolResult:
        valid_name = self._validate_optional_app_name(app_name)

        if app_name is not None and valid_name is None:
            return self._invalid_app_name_result("minimize_window")

        target = valid_name or "active_window"
        decision = self.security.evaluate(create_intent("minimize_window", target))
        security_result = self._security_result_if_blocked("minimize_window", decision)

        if security_result is not None:
            return security_result

        try:
            state = self.macos_tools.minimize_window(valid_name)
        except Exception as error:
            return self._window_error_result("minimize_window", error)

        if state.get("state_confirmed"):
            message = "La fenetre a ete minimisee."
        else:
            message = (
                "La commande de minimisation a ete envoyee, mais Jarvis "
                "n'a pas pu confirmer l'etat de la fenetre."
            )

        return ToolResult.success(
            action="minimize_window",
            message=message,
            **state,
        )

    def maximize_window(self, app_name: str | None = None) -> ToolResult:
        valid_name = self._validate_optional_app_name(app_name)

        if app_name is not None and valid_name is None:
            return self._invalid_app_name_result("maximize_window")

        target = valid_name or "active_window"
        decision = self.security.evaluate(create_intent("maximize_window", target))
        security_result = self._security_result_if_blocked("maximize_window", decision)

        if security_result is not None:
            return security_result

        try:
            state = self.macos_tools.maximize_window(valid_name)
        except Exception as error:
            return self._window_error_result("maximize_window", error)

        if state.get("state_confirmed"):
            message = "La fenetre a ete agrandie."
        else:
            message = (
                "La commande d'agrandissement a ete envoyee, mais Jarvis "
                "n'a pas pu confirmer la position ou la taille de la fenetre."
            )

        return ToolResult.success(
            action="maximize_window",
            message=message,
            **state,
        )

    def move_window(self, position: str, app_name: str | None = None) -> ToolResult:
        valid_position = self._validate_position(position)

        if valid_position is None:
            return ToolResult.failure(
                action="move_window",
                message=(
                    "La position doit etre left, right, center ou fullscreen."
                ),
                error_code="invalid_window_position",
            )

        valid_name = self._validate_optional_app_name(app_name)

        if app_name is not None and valid_name is None:
            return self._invalid_app_name_result("move_window")

        target = f"{valid_name or 'active_window'}:{valid_position}"
        decision = self.security.evaluate(create_intent("move_window", target))
        security_result = self._security_result_if_blocked("move_window", decision)

        if security_result is not None:
            return security_result

        try:
            state = self.macos_tools.move_window(valid_position, valid_name)
        except Exception as error:
            return self._window_error_result("move_window", error)

        if state.get("state_confirmed"):
            message = self._move_success_message(valid_position)
        else:
            message = (
                "La commande de deplacement a ete envoyee, mais Jarvis "
                "n'a pas pu confirmer l'etat de la fenetre."
            )

        return ToolResult.success(
            action="move_window",
            message=message,
            **state,
        )

    def arrange_side_by_side(self, left_app: str, right_app: str) -> ToolResult:
        """Tile two apps side by side: left_app on the left half, right_app on
        the right half. Composes move_window; fails if either move fails."""
        if not (isinstance(left_app, str) and left_app.strip()
                and isinstance(right_app, str) and right_app.strip()):
            return ToolResult.failure(
                action="arrange_windows",
                message="Indique les deux applications a placer cote a cote.",
                error_code="invalid_app_name",
            )
        left = self.move_window("left", left_app.strip())
        if not left.ok:
            return ToolResult.failure(
                action="arrange_windows",
                message=f"Impossible de placer {left_app} a gauche.",
                error_code=left.error_code or "move_failed",
            )
        right = self.move_window("right", right_app.strip())
        if not right.ok:
            return ToolResult.failure(
                action="arrange_windows",
                message=f"{left_app} placee a gauche, mais impossible de placer {right_app} a droite.",
                error_code=right.error_code or "move_failed",
            )
        return ToolResult.success(
            action="arrange_windows",
            message=f"{left_app} a gauche et {right_app} a droite.",
            left_app=left_app.strip(),
            right_app=right_app.strip(),
            left_confirmed=bool(left.data.get("state_confirmed")),
            right_confirmed=bool(right.data.get("state_confirmed")),
        )

    @staticmethod
    def _move_success_message(position: str) -> str:
        if position == "fullscreen":
            return "La fenetre est maintenant en plein ecran."

        return f"La fenetre a ete placee sur {position}."

    @staticmethod
    def _validate_app_name(app_name: str) -> str | None:
        if not isinstance(app_name, str):
            return None

        app_name = app_name.strip()

        if not app_name:
            return None

        return app_name

    @classmethod
    def _validate_optional_app_name(cls, app_name: str | None) -> str | None:
        if app_name is None:
            return None

        return cls._validate_app_name(app_name)

    @classmethod
    def _validate_position(cls, position: str) -> str | None:
        if not isinstance(position, str):
            return None

        position = position.strip().lower()

        if position not in cls.VALID_POSITIONS:
            return None

        return position

    @staticmethod
    def _invalid_app_name_result(action: str) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message="Le nom de l'application est obligatoire.",
            error_code="invalid_app_name",
        )

    @staticmethod
    def _security_result_if_blocked(action: str, decision) -> ToolResult | None:
        if not decision.allowed:
            return ToolResult.failure(
                action=action,
                message="Jarvis n'est pas autorise a controler cette fenetre.",
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
    def _window_error_result(action: str, error: Exception) -> ToolResult:
        message = str(error)
        error_code = "no_window" if "fenetre" in message.lower() else "system_error"

        return ToolResult.failure(
            action=action,
            message=f"Echec du controle de fenetre : {error}",
            error_code=error_code,
        )
