"""Run macOS Shortcuts by name (local, user-authored automations)."""

from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.tools.shortcuts import ShortcutsError, ShortcutsTools


class ShortcutsCapability:
    def __init__(self, shortcuts_tools: ShortcutsTools | None = None):
        self.shortcuts_tools = (
            shortcuts_tools if shortcuts_tools is not None else ShortcutsTools()
        )

    def list_shortcuts(self) -> ToolResult:
        try:
            names = self.shortcuts_tools.list_shortcuts()
        except ShortcutsError as error:
            return ToolResult.failure(
                action="list_shortcuts", message=error.message, error_code=error.code,
            )
        except Exception as error:
            return ToolResult.failure(
                action="list_shortcuts", message=f"Echec : {error}", error_code="system_error",
            )
        return ToolResult.success(
            action="list_shortcuts",
            message=f"{len(names)} raccourci(s) disponible(s).",
            shortcuts=names,
            count=len(names),
        )

    def run_shortcut(self, name: str) -> ToolResult:
        try:
            self.shortcuts_tools.run_shortcut(name)
        except ShortcutsError as error:
            return ToolResult.failure(
                action="run_shortcut", message=error.message, error_code=error.code,
            )
        except Exception as error:
            return ToolResult.failure(
                action="run_shortcut", message=f"Echec : {error}", error_code="system_error",
            )
        return ToolResult.success(
            action="run_shortcut",
            message=f"Raccourci « {name.strip()} » lance.",
            command_executed=True,
            state_confirmed=False,
            shortcut=name.strip(),
        )
