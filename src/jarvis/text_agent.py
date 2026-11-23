"""Text mode backed by the same tool registry as the voice assistant.

The historical REPL (`executor.py`) only knows about forty intents. This mode
sends each typed request to the planner, over the exact LiveKit tools Gemini
Live uses (memory, notes, reminders, files, windows, web…), without a
microphone or a Live session:

    PYTHONPATH=src python -m jarvis.main --outils

Outward actions keep their protocol: they are only prepared; the REPL then
asks « oui / non » and, on « oui », runs confirm_action with that token after
noting the user's turn. A question from the planner is asked back and the
answer resumes the same objective.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from jarvis.planner.engine import PLANNER_TOOL_NAMES, PlannerEngine

# Tools added to the planner allowlist for typed requests: the user is at the
# keyboard, so local writes they ask for (a note, a reminder, a memory) are
# their own decision. Outward ones still go through confirm_action.
TEXT_MODE_EXTRA_TOOLS = (
    "remember", "list_memories", "recent_missions",
    "save_note", "list_notes", "append_note", "manage_checklist",
    "set_reminder", "list_reminders", "cancel_reminder",
    "schedule_message", "list_scheduled_messages",
    "list_calendar_events", "create_calendar_event",
    "calculate", "convert_units", "get_battery_status", "get_system_info",
    "get_storage_status", "get_brightness", "set_brightness",
    "list_macros", "run_macro", "summarize_url",
)
TEXT_MODE_TOOL_NAMES = tuple(dict.fromkeys(PLANNER_TOOL_NAMES + TEXT_MODE_EXTRA_TOOLS))
YES = {"oui", "o", "yes", "y"}


class TextAgent:
    def __init__(self, registry=None, model=None, engine_factory=PlannerEngine):
        if registry is None:
            from jarvis.live.registry import create_live_registry
            registry = create_live_registry()
        if model is None:
            from jarvis.planner.models import build_planner_model
            model = build_planner_model()
        self.registry = registry
        self.tools = registry.livekit_tools()
        self.by_name = {tool.info.name: tool for tool in self.tools}
        self.engine = engine_factory(model, self.tools, allowed=TEXT_MODE_TOOL_NAMES)
        self.loop = asyncio.new_event_loop()
        self.question: str | None = None
        self.goal: str | None = None

    def close(self) -> None:
        if not self.loop.is_closed():
            self.loop.close()

    def _run(self, coroutine):
        return self.loop.run_until_complete(coroutine)

    def respond(self, text: str, ask: Callable[[str], str] = input) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        note = getattr(self.registry, "note_user_turn", None)
        if note is not None:
            note()
        goal = text
        if self.question and self.goal:
            goal = (f"{self.goal}\nPrecision demandee : {self.question}\n"
                    f"Reponse de l'utilisateur : {text}")
        self.question = None
        outcome = self._run(self.engine.run(goal))
        if outcome.status == "needs_clarification":
            self.goal = goal
            self.question = outcome.summary
            return outcome.summary
        self.goal = None
        if outcome.status == "needs_confirmation" and outcome.pending:
            return self._confirm(outcome.pending, ask)
        return outcome.summary

    def _confirm(self, pending: dict[str, Any], ask) -> str:
        token = pending.get("token")
        details = ", ".join(f"{key} : {value}" for key, value in (pending.get("arguments") or {}).items())
        answer = ask(f"Jarvis > Action preparee ({pending.get('tool')}{' · ' + details if details else ''}). "
                     "Confirmer ? (oui/non) ").strip().lower()
        if answer not in YES:
            self._run(self.by_name["cancel_action"](token))
            return "Action annulee, rien n'a ete envoye."
        # The typed « oui » is the user's turn that allows the confirmation.
        note = getattr(self.registry, "note_user_turn", None)
        if note is not None:
            note()
        result = self._run(self.by_name["confirm_action"](token))
        return result.get("message", "Action confirmee.") if isinstance(result, dict) else "Action confirmee."


def start_text_agent(agent: TextAgent | None = None, read=input, write=print) -> None:
    agent = agent or TextAgent()
    write("JARVIS · mode texte avec tous les outils (planificateur). « quit » pour sortir.")
    try:
        while True:
            command = read("Vous > ").strip()
            if not command:
                continue
            if command.lower() in {"quit", "exit", "stop", "au revoir"}:
                write("Jarvis > A bientot.")
                return
            try:
                write(f"\nJarvis > {agent.respond(command, ask=read)}\n")
            except Exception as error:
                write(f"Jarvis > Je rencontre un probleme : {error}")
    finally:
        agent.close()
