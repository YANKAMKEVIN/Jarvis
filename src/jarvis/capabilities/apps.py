from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.macos import MacOSTools


class AppCapability:
    def __init__(
        self,
        security=None,
        macos_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.macos_tools = macos_tools if macos_tools is not None else MacOSTools()

    def open_app(self, app_name: str) -> ToolResult:
        valid_name = self._validate_app_name(app_name)

        if valid_name is None:
            return self._invalid_app_name_result("open_app")

        decision = self.security.evaluate(
            create_intent("open_app", valid_name),
        )

        if not decision.allowed:
            return self._security_denied_result(
                action="open_app",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return self._confirmation_required_result(
                action="open_app",
                reason=decision.reason,
            )

        try:
            message = self.macos_tools.open_app(valid_name)
        except Exception as error:
            return self._system_error_result("open_app", error)

        return ToolResult.success(
            action="open_app",
            message=message,
            target=valid_name,
        )

    def close_app(self, app_name: str) -> ToolResult:
        valid_name = self._validate_app_name(app_name)

        if valid_name is None:
            return self._invalid_app_name_result("close_app")

        decision = self.security.evaluate(
            create_intent("close_app", valid_name),
        )

        if not decision.allowed:
            return self._security_denied_result(
                action="close_app",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return self._confirmation_required_result(
                action="close_app",
                reason=decision.reason,
            )

        try:
            message = self.macos_tools.close_app(valid_name)
        except Exception as error:
            return self._system_error_result("close_app", error)

        return ToolResult.success(
            action="close_app",
            message=message,
            target=valid_name,
        )

    def is_app_running(self, app_name: str) -> ToolResult:
        valid_name = self._validate_app_name(app_name)

        if valid_name is None:
            return self._invalid_app_name_result("is_app_running")

        try:
            running = self.macos_tools.is_app_running(valid_name)
        except Exception as error:
            return self._system_error_result("is_app_running", error)

        if running:
            message = f"{valid_name} est actuellement ouvert."
        else:
            message = f"{valid_name} n'est pas ouvert actuellement."

        return ToolResult.success(
            action="is_app_running",
            message=message,
            target=valid_name,
            running=running,
        )

    @staticmethod
    def _validate_app_name(app_name: str) -> str | None:
        if not isinstance(app_name, str):
            return None

        app_name = app_name.strip()

        if not app_name:
            return None

        return app_name

    @staticmethod
    def _invalid_app_name_result(action: str) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message="Le nom de l'application est obligatoire.",
            error_code="invalid_app_name",
        )

    @staticmethod
    def _security_denied_result(action: str, reason: str) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message="Jarvis n'est pas autorise a controler cette application.",
            error_code="security_denied",
            reason=reason,
        )

    @staticmethod
    def _confirmation_required_result(action: str, reason: str) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=(
                "Cette action necessite une confirmation non disponible "
                "en mode Live."
            ),
            error_code="confirmation_required",
            requires_confirmation=True,
            reason=reason,
        )

    @staticmethod
    def _system_error_result(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=f"Echec du controle de l'application : {error}",
            error_code="system_error",
        )
