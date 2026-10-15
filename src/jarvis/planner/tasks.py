"""Background planner tasks for the voice session.

run_task must answer immediately (a realtime voice model cannot wait a
minute on a tool call), so the engine runs as an asyncio task. One task at a
time; it can be polled (status) or cancelled, and on completion an
announcement is handed to the voice layer, which speaks it.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Awaitable, Callable

from jarvis.planner.engine import PlannerEngine, StepRecord, TaskOutcome


MAX_GOAL_LENGTH = 500

OnFinished = Callable[[str, TaskOutcome], Awaitable[None]]


class TaskManager:
    def __init__(
        self,
        engine_factory: Callable[[], PlannerEngine],
        on_finished: OnFinished | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.engine_factory = engine_factory
        self.on_finished = on_finished
        self.clock = clock if clock is not None else time.monotonic
        self._task: asyncio.Task | None = None
        self._cancel = threading.Event()
        self._goal: str | None = None
        self._steps: list[StepRecord] = []
        self._started = 0.0
        self._outcome: TaskOutcome | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, goal: str) -> dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip():
            return {"ok": False, "error_code": "invalid_goal",
                    "message": "L'objectif de la tache est vide."}
        if len(goal) > MAX_GOAL_LENGTH:
            return {"ok": False, "error_code": "goal_too_long",
                    "message": f"Objectif trop long ({MAX_GOAL_LENGTH} caracteres max)."}
        if self.running:
            return {
                "ok": False,
                "error_code": "task_already_running",
                "message": "Une tache est deja en cours. Attends sa fin ou annule-la.",
            }

        self._goal = goal.strip()
        self._cancel = threading.Event()
        self._steps = []
        self._outcome = None
        self._started = self.clock()
        self._task = asyncio.get_running_loop().create_task(self._run(self._goal, self._cancel))
        return {
            "ok": True,
            "task_started": True,
            "message": (
                "Tache lancee en arriere-plan. Dis simplement a l'utilisateur que "
                "tu t'en occupes ; le resultat sera annonce a la fin."
            ),
        }

    def status(self) -> dict[str, Any]:
        if self.running:
            last = self._steps[-1].tool if self._steps else None
            return {
                "ok": True,
                "running": True,
                "goal": self._goal,
                "step_count": len(self._steps),
                "last_tool": last,
                "elapsed_seconds": int(self.clock() - self._started),
                "message": "Une tache est en cours.",
            }
        if self._outcome is not None:
            return {
                "ok": True,
                "running": False,
                "goal": self._goal,
                "last_task": self._outcome.to_dict(),
                "message": "Aucune tache en cours ; voici la derniere.",
            }
        return {"ok": True, "running": False, "message": "Aucune tache lancee."}

    def cancel(self) -> dict[str, Any]:
        if not self.running:
            return {"ok": True, "cancel_requested": False,
                    "message": "Aucune tache en cours a annuler."}
        self._cancel.set()
        return {
            "ok": True,
            "cancel_requested": True,
            "message": "Annulation demandee : la tache s'arrete avant l'etape suivante.",
        }

    def last_completed(self) -> tuple[str, list[str]] | None:
        """The last successfully completed task as (goal, ordered ok tool names).

        Used to learn a reusable procedure from a task that just worked. Only
        tool names are exposed — never arguments or content.
        """
        if (
            self._outcome is not None
            and self._outcome.status == "completed"
            and isinstance(self._goal, str)
            and self._goal.strip()
        ):
            tools = [step.tool for step in self._outcome.steps if step.ok]
            if tools:
                return self._goal, tools
        return None

    async def wait(self) -> TaskOutcome | None:
        """Await the current task (tests and shutdown)."""
        if self._task is not None:
            await asyncio.shield(self._task)
        return self._outcome

    async def _run(self, goal: str, cancel: threading.Event) -> None:
        try:
            engine = self.engine_factory()
            outcome = await engine.run(goal, cancel, on_step=self._steps.append)
        except Exception as error:
            outcome = TaskOutcome("failed", f"Erreur interne de la tache : {error}", list(self._steps))
        self._outcome = outcome

        if self.on_finished is not None:
            try:
                await self.on_finished(goal, outcome)
            except Exception:
                pass


def announcement_for(goal: str, outcome: TaskOutcome) -> str:
    """Instructions for the voice model to speak a finished task's result."""
    if outcome.status == "needs_confirmation" and outcome.pending:
        arguments = outcome.pending.get("arguments") or {}
        token = outcome.pending.get("token")
        app = arguments.get("app_name") or outcome.pending.get("target_app") or "l'application"
        recipient = arguments.get("recipient") or "la conversation ouverte"
        text = arguments.get("text") or ""
        return (
            "La tache en arriere-plan a PREPARE un message, rien n'est encore envoye. "
            f"Application : {app}. Destinataire : {recipient}. Message : « {text} ». "
            "Annonce ces trois elements a l'utilisateur et demande une confirmation "
            f"explicite. Seulement sur un oui clair, appelle confirm_action(token=\"{token}\") ; "
            f"sinon appelle cancel_action(token=\"{token}\")."
        )
    if outcome.status == "completed":
        return (
            f"La tache « {goal} » est terminee. Resultat du planificateur : {outcome.summary} "
            "Annonce ce resultat a l'utilisateur en une ou deux phrases, sans detailler les "
            "etapes, et sans affirmer ce que le resultat ne confirme pas."
        )
    if outcome.status == "cancelled":
        return "La tache en arriere-plan a ete annulee. Confirme-le brievement."
    return (
        f"La tache « {goal} » n'a pas abouti. Raison : {outcome.summary} "
        "Dis-le brievement a l'utilisateur et propose de reessayer ou de le faire "
        "autrement, sans inventer de resultat."
    )
