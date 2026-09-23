from __future__ import annotations

from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.filesystem import FileSystemError, FileSystemTools


class FilesCapability:
    def __init__(
        self,
        security=None,
        filesystem_tools=None,
    ):
        self.security = security if security is not None else SecurityManager()
        self.filesystem_tools = (
            filesystem_tools
            if filesystem_tools is not None
            else FileSystemTools()
        )

    def list_files(self, path: str | None = None) -> ToolResult:
        try:
            state = self.filesystem_tools.list_files(path)
        except FileSystemError as error:
            return self._filesystem_failure("list_files", error)
        except Exception as error:
            return self._system_error_result("list_files", error)

        result_count = state.get("result_count", 0)
        message = f"{result_count} element(s) trouve(s) dans le dossier."

        if state.get("truncated"):
            message += " La liste est tronquee."

        return ToolResult.success(
            action="list_files",
            message=message,
            **state,
        )

    def find_files(self, query: str, path: str | None = None) -> ToolResult:
        try:
            state = self.filesystem_tools.find_files(query, path)
        except FileSystemError as error:
            return self._filesystem_failure("find_files", error)
        except Exception as error:
            return self._system_error_result("find_files", error)

        result_count = state.get("result_count", 0)

        if result_count:
            message = f"{result_count} fichier(s) ou dossier(s) correspondent."
        else:
            message = "Aucun fichier ou dossier ne correspond a la recherche."

        if state.get("truncated"):
            message += " Les resultats sont tronques."

        return ToolResult.success(
            action="find_files",
            message=message,
            **state,
        )

    def get_file_info(self, path: str) -> ToolResult:
        try:
            state = self.filesystem_tools.get_file_info(path)
        except FileSystemError as error:
            return self._filesystem_failure("get_file_info", error)
        except Exception as error:
            return self._system_error_result("get_file_info", error)

        return ToolResult.success(
            action="get_file_info",
            message=f"Informations disponibles pour {state.get('name')}.",
            **state,
        )

    def open_file(self, path: str) -> ToolResult:
        security_result = self._security_result("open_file", path)

        if security_result is not None:
            return security_result

        try:
            state = self.filesystem_tools.open_file(path)
        except FileSystemError as error:
            return self._filesystem_failure("open_file", error)
        except Exception as error:
            return self._system_error_result("open_file", error)

        return ToolResult.success(
            action="open_file",
            message=(
                "La commande d'ouverture du fichier a ete envoyee, mais "
                "Jarvis ne peut pas confirmer visuellement l'ouverture."
            ),
            **state,
        )

    def open_folder(self, path: str) -> ToolResult:
        security_result = self._security_result("open_folder", path)

        if security_result is not None:
            return security_result

        try:
            state = self.filesystem_tools.open_folder(path)
        except FileSystemError as error:
            return self._filesystem_failure("open_folder", error)
        except Exception as error:
            return self._system_error_result("open_folder", error)

        return ToolResult.success(
            action="open_folder",
            message=(
                "La commande d'ouverture du dossier a ete envoyee, mais "
                "Jarvis ne peut pas confirmer visuellement l'ouverture."
            ),
            **state,
        )

    def create_folder(self, path: str) -> ToolResult:
        security_result = self._security_result("create_folder", path)

        if security_result is not None:
            return security_result

        try:
            state = self.filesystem_tools.create_folder(path)
        except FileSystemError as error:
            return self._filesystem_failure("create_folder", error)
        except Exception as error:
            return self._system_error_result("create_folder", error)

        if state.get("state_confirmed"):
            message = "Le dossier a ete cree et son existence a ete confirmee."
        else:
            message = (
                "La commande de creation du dossier a ete executee, mais "
                "Jarvis n'a pas pu confirmer l'etat final."
            )

        return ToolResult.success(
            action="create_folder",
            message=message,
            **state,
        )

    def rename_file(self, path: str, new_name: str) -> ToolResult:
        security_result = self._security_result("rename_file", path)

        if security_result is not None:
            return security_result

        try:
            state = self.filesystem_tools.rename_file(path, new_name)
        except FileSystemError as error:
            return self._filesystem_failure("rename_file", error)
        except Exception as error:
            return self._system_error_result("rename_file", error)

        if state.get("state_confirmed"):
            message = "Le fichier ou dossier a ete renomme et verifie."
        else:
            message = (
                "La commande de renommage a ete executee, mais Jarvis "
                "n'a pas pu confirmer l'etat final."
            )

        return ToolResult.success(
            action="rename_file",
            message=message,
            **state,
        )

    def move_file(self, source: str, destination: str) -> ToolResult:
        security_result = self._security_result("move_file", source)

        if security_result is not None:
            return security_result

        try:
            state = self.filesystem_tools.move_file(source, destination)
        except FileSystemError as error:
            return self._filesystem_failure("move_file", error)
        except Exception as error:
            return self._system_error_result("move_file", error)

        if state.get("state_confirmed"):
            message = "Le fichier ou dossier a ete deplace et verifie."
        else:
            message = (
                "La commande de deplacement a ete executee, mais Jarvis "
                "n'a pas pu confirmer l'etat final."
            )

        return ToolResult.success(
            action="move_file",
            message=message,
            **state,
        )

    def _security_result(self, action: str, target: str | None) -> ToolResult | None:
        decision = self.security.evaluate(create_intent(action, target))

        if not decision.allowed:
            return ToolResult.failure(
                action=action,
                message="Jarvis n'est pas autorise a effectuer cette action fichier.",
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
    def _filesystem_failure(action: str, error: FileSystemError) -> ToolResult:
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
            message=f"Echec de l'operation fichier : {error}",
            error_code="system_error",
        )
