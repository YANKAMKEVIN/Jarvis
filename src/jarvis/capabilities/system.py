import shutil

from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.macos import MacOSTools


LOW_SPACE_PERCENT = 10


class SystemCapability:
    def __init__(
        self,
        security=None,
        macos_tools=None,
        disk_usage=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.macos_tools = macos_tools if macos_tools is not None else MacOSTools()
        self._disk_usage = disk_usage if disk_usage is not None else shutil.disk_usage

    def get_storage_status(self, path: str = "/") -> ToolResult:
        try:
            usage = self._disk_usage(path)
        except Exception as error:
            return self._system_error_result("get_storage_status", error)

        total = int(usage.total)
        free = int(usage.free)
        used = total - free
        free_gb = round(free / 1e9, 1)
        total_gb = round(total / 1e9, 1)
        percent_free = round(free / total * 100) if total else 0
        low = percent_free < LOW_SPACE_PERCENT

        if low:
            message = (
                f"Attention, il ne reste que {free_gb} Go libres sur {total_gb} Go "
                f"({percent_free} %)."
            )
        else:
            message = f"Il reste {free_gb} Go libres sur {total_gb} Go ({percent_free} %)."

        return ToolResult.success(
            action="get_storage_status",
            message=message,
            free_bytes=free,
            used_bytes=used,
            total_bytes=total,
            free_gb=free_gb,
            total_gb=total_gb,
            percent_free=percent_free,
            low_space=low,
        )

    def get_battery_status(self) -> ToolResult:
        try:
            status = self.macos_tools.get_battery_status()
        except Exception as error:
            return self._system_error_result("get_battery_status", error)

        percentage = status.get("percentage")
        charging = status.get("charging")

        if charging:
            message = f"La batterie est a {percentage} % et le Mac est en charge."
        else:
            message = f"La batterie est a {percentage} %."

        return ToolResult.success(
            action="get_battery_status",
            message=message,
            **status,
        )

    def get_system_info(self) -> ToolResult:
        try:
            info = self.macos_tools.get_system_info()
        except Exception as error:
            return self._system_error_result("get_system_info", error)

        model_name = info.get("model_name") or "Mac"
        chip = info.get("chip")

        if chip:
            message = f"Tu utilises un {model_name} avec {chip}."
        else:
            message = f"Tu utilises un {model_name}."

        return ToolResult.success(
            action="get_system_info",
            message=message,
            **info,
        )

    def get_brightness(self) -> ToolResult:
        try:
            brightness = int(self.macos_tools.get_brightness())
        except Exception as error:
            return self._system_error_result("get_brightness", error)

        return ToolResult.success(
            action="get_brightness",
            message=f"La luminosite actuelle est de {brightness} %.",
            brightness=brightness,
        )

    def set_brightness(self, level: int) -> ToolResult:
        try:
            requested = int(level)
        except (TypeError, ValueError):
            return ToolResult.failure(
                action="set_brightness",
                message="La luminosite doit etre un nombre entier entre 0 et 100.",
                error_code="invalid_brightness",
            )

        if not 0 <= requested <= 100:
            return ToolResult.failure(
                action="set_brightness",
                message="La luminosite doit etre comprise entre 0 et 100.",
                error_code="brightness_out_of_range",
            )

        decision = self.security.evaluate(
            create_intent("set_brightness", str(requested)),
        )

        if not decision.allowed:
            return self._security_denied_result(
                action="set_brightness",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return self._confirmation_required_result(
                action="set_brightness",
                reason=decision.reason,
            )

        try:
            state = self.macos_tools.set_brightness(requested)
        except Exception as error:
            return self._system_error_result("set_brightness", error)

        observed = state.get("brightness")

        return ToolResult.success(
            action="set_brightness",
            message=f"La luminosite est maintenant observee a {observed} %.",
            **state,
        )

    def lock_screen(self) -> ToolResult:
        decision = self.security.evaluate(create_intent("lock_screen"))

        if not decision.allowed:
            return self._security_denied_result(
                action="lock_screen",
                reason=decision.reason,
            )

        if decision.requires_confirmation:
            return self._confirmation_required_result(
                action="lock_screen",
                reason=decision.reason,
            )

        try:
            state = self.macos_tools.lock_screen()
        except Exception as error:
            return self._system_error_result("lock_screen", error)

        if state.get("state_confirmed") and state.get("locked"):
            message = "Mac verrouille."
        elif state.get("command_executed"):
            message = (
                "La commande de verrouillage a ete envoyee, mais Jarvis "
                "n'a pas pu confirmer que le Mac est verrouille."
            )
        else:
            message = "Jarvis n'a pas pu confirmer le verrouillage du Mac."

        return ToolResult.success(
            action="lock_screen",
            message=message,
            **state,
        )

    @staticmethod
    def _security_denied_result(action: str, reason: str) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message="Jarvis n'est pas autorise a modifier cet etat systeme.",
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
            message=f"Echec de la lecture ou action systeme : {error}",
            error_code="system_error",
        )
