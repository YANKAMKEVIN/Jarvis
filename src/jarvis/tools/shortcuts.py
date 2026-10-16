"""Run macOS Shortcuts by name via the `shortcuts` CLI.

A reliable, general way to reach automations the user has built -- including
Focus / Do Not Disturb, which has no clean programmatic API on recent macOS: the
user makes a Shortcut and Jarvis runs it by name. The runner is injectable so
flows are testable without the real CLI.
"""

from __future__ import annotations

import subprocess
from typing import Callable


Runner = Callable[[list[str]], "tuple[int, str, str]"]


class ShortcutsError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


def _default_runner(argv: list[str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return 127, "", "__no_cli__"
    except subprocess.TimeoutExpired:
        return 1, "", "__timeout__"
    return completed.returncode, completed.stdout, completed.stderr


class ShortcutsTools:
    def __init__(self, runner: Runner | None = None):
        self._run = runner if runner is not None else _default_runner

    def list_shortcuts(self) -> list[str]:
        code, stdout, stderr = self._run(["shortcuts", "list"])
        if code != 0:
            raise ShortcutsError(*self._error(stderr, "liste"))
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    def run_shortcut(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ShortcutsError("Le nom du raccourci est obligatoire.", "invalid_name")
        code, stdout, stderr = self._run(["shortcuts", "run", name.strip()])
        if code != 0:
            # The CLI returns non-zero for an unknown shortcut too.
            raise ShortcutsError(*self._error(stderr, "execution", name.strip()))

    @staticmethod
    def _error(stderr: str, what: str, name: str | None = None) -> tuple[str, str]:
        detail = stderr.strip()
        if detail == "__no_cli__":
            return "La commande Shortcuts n'est pas disponible sur ce Mac.", "shortcuts_unavailable"
        if detail == "__timeout__":
            return "Le raccourci a mis trop de temps a repondre.", "shortcuts_timeout"
        if name is not None:
            return (
                f"Le raccourci « {name} » est introuvable ou a echoue"
                + (f" : {detail}" if detail else "."),
                "shortcut_failed",
            )
        return (
            "Impossible de lire la liste des raccourcis"
            + (f" : {detail}" if detail else "."),
            "shortcuts_failed",
        )
