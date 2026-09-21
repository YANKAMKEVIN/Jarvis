from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.macos import MacOSTools


class AudioCapability:
    def __init__(
        self,
        security=None,
        macos_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.macos_tools = macos_tools if macos_tools is not None else MacOSTools()

    def set_volume(self, volume: int) -> ToolResult:
        try:
            level = int(volume)
        except (TypeError, ValueError):
            return ToolResult.failure(
                action="set_volume",
                message="Le volume doit etre un nombre entier entre 0 et 100.",
                error_code="invalid_volume",
            )

        if not 0 <= level <= 100:
            return ToolResult.failure(
                action="set_volume",
                message="Le volume doit etre compris entre 0 et 100.",
                error_code="volume_out_of_range",
            )

        intent = create_intent("set_volume", str(level))
        decision = self.security.evaluate(intent)

        if not decision.allowed:
            return ToolResult.failure(
                action="set_volume",
                message="Jarvis n'est pas autorise a modifier le volume.",
                error_code="security_denied",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return ToolResult.failure(
                action="set_volume",
                message=(
                    "Cette action necessite une confirmation non disponible "
                    "en mode Live."
                ),
                error_code="confirmation_required",
                requires_confirmation=True,
                reason=decision.reason,
            )

        try:
            message = self.macos_tools.set_volume(level)
        except Exception as error:
            return ToolResult.failure(
                action="set_volume",
                message=f"Echec du reglage du volume : {error}",
                error_code="system_error",
            )

        return ToolResult.success(
            action="set_volume",
            message=message,
            volume=level,
        )

    def get_volume(self) -> ToolResult:
        try:
            volume = self.macos_tools.get_volume()
            level = int(volume)
        except Exception as error:
            return ToolResult.failure(
                action="get_volume",
                message=f"Echec de la lecture du volume actuel : {error}",
                error_code="system_error",
            )

        return ToolResult.success(
            action="get_volume",
            message=f"Le volume actuel est de {level} %.",
            volume=level,
        )
