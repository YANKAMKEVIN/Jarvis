"""Drive the local `claude` CLI: one-shot headless tasks and opening an
interactive session in Terminal. Thin and injectable (runner/opener) so the
capability is testable without spawning a real agent. Nothing here skips Claude
Code's own permission prompts -- a one-shot runs with default permissions.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from typing import Callable


class ClaudeCliError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


class ClaudeCli:
    def __init__(self, binary: str | None = None,
                 runner: Callable | None = None,
                 opener: Callable | None = None):
        self._binary = binary
        self._runner = runner if runner is not None else subprocess.run
        self._opener = opener if opener is not None else subprocess.run

    def resolve(self) -> str | None:
        if self._binary:
            return self._binary
        return shutil.which("claude")

    def available(self) -> bool:
        return self.resolve() is not None

    def run_once(self, prompt: str, cwd: str | None = None, timeout: int = 300) -> dict:
        """Run `claude -p <prompt> --output-format json` and parse the result."""
        binary = self.resolve()
        if not binary:
            raise ClaudeCliError("Le CLI claude est introuvable.", "claude_missing")
        cmd = [binary, "-p", prompt, "--output-format", "json"]
        try:
            completed = self._runner(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ClaudeCliError("La session Claude a dépassé le délai.", "timeout")
        except OSError as error:
            raise ClaudeCliError(f"Lancement impossible : {error}", "spawn_failed")
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip().splitlines()
            raise ClaudeCliError(
                detail[-1] if detail else "La session Claude a échoué.",
                "claude_failed",
            )
        try:
            data = json.loads(completed.stdout)
        except (ValueError, TypeError):
            raise ClaudeCliError("Réponse de Claude illisible.", "bad_output")
        usage = data.get("usage") or {}
        return {
            "result": (data.get("result") or "").strip(),
            "is_error": bool(data.get("is_error")),
            "num_turns": data.get("num_turns"),
            "session_id": data.get("session_id"),
            "cost_usd": data.get("total_cost_usd"),
            "output_tokens": usage.get("output_tokens"),
        }

    def open_interactive(self, cwd: str | None = None) -> None:
        """Open Terminal.app and start an interactive `claude` session in cwd."""
        if not self.available():
            raise ClaudeCliError("Le CLI claude est introuvable.", "claude_missing")
        directory = cwd or os.path.expanduser("~")
        command = f"cd {shlex.quote(directory)} && claude"
        script = f'tell application "Terminal"\nactivate\ndo script {_osa_quote(command)}\nend tell'
        try:
            self._opener(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=15, check=True,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "").strip()
            raise ClaudeCliError(detail or "Ouverture du Terminal impossible.", "open_failed")
        except subprocess.TimeoutExpired:
            raise ClaudeCliError("Ouverture du Terminal trop longue.", "timeout")
        except OSError as error:
            raise ClaudeCliError(f"Ouverture impossible : {error}", "open_failed")


def _osa_quote(text: str) -> str:
    """Quote a string as an AppleScript string literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
