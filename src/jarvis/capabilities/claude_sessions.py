"""Launch Claude Code sessions from Jarvis: a headless one-shot task whose
answer is read back, or an interactive session opened in Terminal. Both are
outward, consequential actions, so the registry gates them behind an explicit
confirmation; these methods are the executors that run only once confirmed.
"""

from __future__ import annotations

import os

from jarvis.capabilities.results import ToolResult
from jarvis.tools.claude_cli import ClaudeCli, ClaudeCliError

_MAX_PROMPT_CHARS = 4000
_MAX_SPOKEN_RESULT = 600


class ClaudeSessionsCapability:
    def __init__(self, cli: ClaudeCli | None = None, default_dir: str | None = None):
        self.cli = cli if cli is not None else ClaudeCli()
        self._default_dir = default_dir if default_dir is not None else os.path.expanduser("~")

    def available(self) -> bool:
        return self.cli.available()

    def _resolve_dir(self, directory: str | None) -> str:
        if directory:
            path = os.path.expanduser(str(directory))
            if os.path.isdir(path):
                return path
        return self._default_dir

    def resolve_directory(self, directory: str | None = None) -> str:
        """Public: the directory a task/session would actually run in."""
        return self._resolve_dir(directory)

    def run_task(self, prompt: str, directory: str | None = None) -> ToolResult:
        if not isinstance(prompt, str) or not prompt.strip():
            return ToolResult.failure("run_claude_task",
                                      "La consigne pour Claude est vide.", "invalid_prompt")
        if not self.available():
            return ToolResult.failure("run_claude_task",
                                      "Le CLI claude est introuvable.", "claude_missing")
        cwd = self._resolve_dir(directory)
        try:
            out = self.cli.run_once(prompt.strip()[:_MAX_PROMPT_CHARS], cwd=cwd)
        except ClaudeCliError as error:
            return ToolResult.failure("run_claude_task", error.message, error.code)
        if out["is_error"]:
            return ToolResult.failure("run_claude_task",
                                      f"La session Claude a renvoyé une erreur : {out['result'][:200]}",
                                      "claude_error")
        answer = out["result"] or "(réponse vide)"
        spoken = answer[:_MAX_SPOKEN_RESULT]
        if len(answer) > _MAX_SPOKEN_RESULT:
            spoken += "…"
        turns = out.get("num_turns")
        prefix = f"Session Claude terminée ({turns} tour(s)). " if turns else "Session Claude terminée. "
        return ToolResult.success("run_claude_task", prefix + "Réponse : " + spoken,
                                  result=answer, directory=cwd,
                                  session_id=out.get("session_id"),
                                  cost_usd=out.get("cost_usd"),
                                  output_tokens=out.get("output_tokens"))

    def open_session(self, directory: str | None = None) -> ToolResult:
        if not self.available():
            return ToolResult.failure("open_claude_session",
                                      "Le CLI claude est introuvable.", "claude_missing")
        cwd = self._resolve_dir(directory)
        try:
            self.cli.open_interactive(cwd)
        except ClaudeCliError as error:
            return ToolResult.failure("open_claude_session", error.message, error.code)
        return ToolResult.success("open_claude_session",
                                  f"Session Claude ouverte dans le Terminal, dossier {cwd}.",
                                  directory=cwd)
