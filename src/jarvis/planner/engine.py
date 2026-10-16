"""Planning loop: plan -> execute -> verify -> correct, over Jarvis' own tools.

The engine drives the exact LiveKit tools Gemini uses (same locks, state
verification, journal and locally applied memory), restricted to an
allowlist. It enforces budgets, never confirms an outward action itself
(the task pauses with the token so the user confirms by voice), and can be
cancelled between steps.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from jarvis.planner.models import ModelTurn, PlannerModel, PlannerModelError, ToolCall


# Allowlist, not denylist: a new tool is never exposed to the planner by
# accident. Deliberately absent: confirm_action / cancel_action (the user
# confirms outward actions by voice), lock_screen, raw mouse/keyboard
# primitives (blind clicks or keystrokes), remember / forget / propose_memory
# (memory writes stay a conversation decision), brightness, vision.
PLANNER_TOOL_NAMES = (
    "open_app",
    "close_app",
    "is_app_running",
    "focus_window",
    "get_active_window",
    "browse_open_url",
    "browse_search_web",
    "browse_get_active_tab",
    "browse_list_tabs",
    "browse_activate_tab",
    "list_files",
    "find_files",
    "get_file_info",
    "open_file",
    "open_folder",
    "create_folder",
    "rename_file",
    "move_file",
    "get_clipboard_text",
    "set_clipboard_text",
    "select_all_and_copy",
    "focus_app_ui_and_type",
    "open_app_and_focus_ui",
    "find_ui_elements",
    "activate_ui_element",
    "send_prompt_to_app",
    "prepare_send_message",
    "get_volume",
    "set_volume",
    "play_pause",
    "next_track",
    "previous_track",
    "get_media_state",
    "capture_screen",
    "capture_window",
    "recall",
    "recent_activity",
    "web_answer",
)

DEFAULT_MAX_STEPS = 25
DEFAULT_MAX_SECONDS = 180.0
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3
# Keeps several steps inside a small local context window.
MAX_TOOL_RESULT_CHARS = 1200

PLANNER_SYSTEM_PROMPT = """
Tu es le planificateur de Jarvis, l'assistant de l'utilisateur sur son Mac. Tu recois un objectif et tu l'accomplis en appelant les tools fournis, un a la fois.
Methode : decoupe l'objectif en etapes courtes ; appelle un tool ; lis son resultat ; continue seulement si l'etape a reussi.
Verification : une etape n'a reussi que si ok=true. Si state_confirmed=false, l'effet n'est pas confirme : relis l'etat avec un tool de lecture (get_active_window, browse_get_active_tab, list_files...) avant d'en dependre.
Correction : si une etape echoue, essaie une autre approche sure une seule fois (par exemple focaliser l'application ou le champ avant de taper). Si tu restes bloque, arrete-toi et explique pourquoi.
Clarification : si une information ESSENTIELLE te manque pour continuer et que tu ne peux pas l'obtenir toi-meme avec un tool (par exemple le nom exact d'un destinataire, un choix ambigu), appelle ask_clarification(question) avec UNE question courte et precise. N'appelle ask_clarification qu'en dernier recours, jamais pour une information que tu peux recuperer (recall, lecture d'etat).
N'invente jamais un chemin, un nom de contact, une URL ou un resultat. Utilise recall pour une information personnelle (un proche, une preference).
Pour une information a jour que tu n'as pas (actualites, prix, meteo, faits recents, "qui est"), utilise web_answer avec la question ; appuie-toi uniquement sur sa reponse et ses sources, sans rien inventer.
Messages : prepare_send_message prepare un envoi sans l'envoyer ; l'utilisateur confirmera lui-meme ensuite. Ne cherche jamais a envoyer autrement.
Quand l'objectif est atteint ou impossible, reponds sans appeler de tool : une ou deux phrases en francais qui disent ce qui a ete fait, ce qui est confirme et ce qui ne l'est pas.
""".strip()


@dataclass
class StepRecord:
    tool: str
    ok: bool
    state_confirmed: bool | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"tool": self.tool, "ok": self.ok}
        if self.state_confirmed is not None:
            payload["state_confirmed"] = self.state_confirmed
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload


@dataclass
class TaskOutcome:
    # completed | needs_confirmation | failed | budget_exceeded | cancelled
    status: str
    summary: str
    steps: list[StepRecord] = field(default_factory=list)
    pending: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
            "step_count": len(self.steps),
        }
        if self.pending:
            payload["pending"] = self.pending
        return payload


_ASK_CLARIFICATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_clarification",
        "description": (
            "Pose UNE question courte a l'utilisateur quand une information "
            "essentielle manque pour continuer et ne peut pas etre obtenue "
            "autrement. La tache s'arrete en attendant sa reponse."
        ),
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
}


def tool_schema(tool) -> dict:
    from livekit.agents.llm.utils import build_legacy_openai_schema

    return build_legacy_openai_schema(tool)


class PlannerEngine:
    def __init__(
        self,
        model: PlannerModel,
        tools: list[Any],
        allowed: tuple[str, ...] = PLANNER_TOOL_NAMES,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_seconds: float = DEFAULT_MAX_SECONDS,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
        clock: Callable[[], float] | None = None,
        system_prompt: str = PLANNER_SYSTEM_PROMPT,
    ):
        self.model = model
        allowed_set = set(allowed)
        self.tools = {
            tool.info.name: tool for tool in tools if tool.info.name in allowed_set
        }
        # Synthetic tool: the engine intercepts it (not a real capability) to
        # pause the task and have the voice layer ask the user one question.
        schemas = [tool_schema(self.tools[name]) for name in self.tools]
        schemas.append(_ASK_CLARIFICATION_SCHEMA)
        # Deterministic sorted order keeps the prompt prefix stable (cache-friendly).
        self.schemas = sorted(schemas, key=lambda s: s["function"]["name"])
        self.max_steps = max(1, int(max_steps))
        self.max_seconds = float(max_seconds)
        self.max_consecutive_failures = max(1, int(max_consecutive_failures))
        self.clock = clock if clock is not None else time.monotonic
        self.system_prompt = system_prompt

    async def run(
        self,
        goal: str,
        cancel: threading.Event | None = None,
        on_step: Callable[[StepRecord], None] | None = None,
    ) -> TaskOutcome:
        if not isinstance(goal, str) or not goal.strip():
            return TaskOutcome("failed", "L'objectif de la tache est vide.")

        cancel = cancel or threading.Event()
        started = self.clock()
        steps: list[StepRecord] = []
        consecutive_failures = 0
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": goal.strip()},
        ]

        while True:
            stop = self._check_limits(cancel, started, steps)
            if stop is not None:
                return stop

            try:
                turn: ModelTurn = await asyncio.to_thread(
                    self.model.complete, messages, self.schemas,
                )
            except PlannerModelError as error:
                return TaskOutcome("failed", error.message, steps)
            except Exception as error:
                return TaskOutcome("failed", f"Erreur du modele : {error}", steps)

            if not turn.tool_calls:
                summary = turn.text or "Tache terminee, sans resume du modele."
                return TaskOutcome("completed", summary, steps)

            messages.append(
                {"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls}
            )

            for call in turn.tool_calls:
                stop = self._check_limits(cancel, started, steps)
                if stop is not None:
                    return stop

                if call.name == "ask_clarification":
                    question = str(call.arguments.get("question") or "").strip()
                    return TaskOutcome(
                        "needs_clarification",
                        question or "J'ai besoin d'une precision pour continuer.",
                        steps,
                        pending={"question": question},
                    )

                result = await self._execute(call)
                record = StepRecord(
                    tool=call.name,
                    ok=bool(result.get("ok")),
                    state_confirmed=result.get("state_confirmed"),
                    error_code=result.get("error_code"),
                )
                steps.append(record)
                if on_step is not None:
                    try:
                        on_step(record)
                    except Exception:
                        pass
                messages.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "tool_call_id": call.id,
                        "content": self._serialize(result),
                    }
                )

                if result.get("requires_confirmation") and result.get("token"):
                    # Outward action prepared: hand control back to the voice
                    # layer, which announces it and asks the user.
                    return TaskOutcome(
                        "needs_confirmation",
                        "Une action sortante a ete preparee et attend la "
                        "confirmation de l'utilisateur.",
                        steps,
                        pending={
                            "token": result["token"],
                            "tool": call.name,
                            "target_app": result.get("target_app"),
                            # What was prepared, so the user can confirm
                            # knowingly. Never journaled.
                            "arguments": dict(call.arguments),
                        },
                    )

                consecutive_failures = 0 if record.ok else consecutive_failures + 1
                if consecutive_failures >= self.max_consecutive_failures:
                    return TaskOutcome(
                        "failed",
                        f"Arret apres {consecutive_failures} echecs consecutifs "
                        f"(dernier : {call.name}, {record.error_code or 'erreur'}).",
                        steps,
                    )

    def _check_limits(self, cancel, started, steps) -> TaskOutcome | None:
        if cancel.is_set():
            return TaskOutcome("cancelled", "Tache annulee a la demande.", steps)
        if len(steps) >= self.max_steps:
            return TaskOutcome(
                "budget_exceeded",
                f"Arret apres {len(steps)} etapes sans terminer la tache.",
                steps,
            )
        if self.clock() - started >= self.max_seconds:
            return TaskOutcome(
                "budget_exceeded",
                f"Arret apres {int(self.max_seconds)} secondes sans terminer la tache.",
                steps,
            )
        return None

    async def _execute(self, call: ToolCall) -> dict:
        tool = self.tools.get(call.name)
        if tool is None:
            return {
                "ok": False,
                "error_code": "tool_not_allowed",
                "message": f"Le tool {call.name or '(vide)'} n'est pas disponible.",
            }
        if "__invalid_json__" in call.arguments:
            return {
                "ok": False,
                "error_code": "invalid_arguments",
                "message": "Les arguments ne sont pas du JSON valide.",
            }
        try:
            result = await tool(**call.arguments)
        except TypeError as error:
            return {
                "ok": False,
                "error_code": "invalid_arguments",
                "message": f"Arguments invalides pour {call.name} : {error}",
            }
        except Exception as error:
            return {
                "ok": False,
                "error_code": "tool_error",
                "message": f"Erreur pendant {call.name} : {error}",
            }
        return result if isinstance(result, dict) else {"ok": False, "error_code": "bad_result"}

    @staticmethod
    def _serialize(result: dict) -> str:
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > MAX_TOOL_RESULT_CHARS:
            text = text[:MAX_TOOL_RESULT_CHARS] + "... (tronque)"
        return text
