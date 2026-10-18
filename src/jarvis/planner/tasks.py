"""Background planner tasks for the voice session.

run_task must answer immediately (a realtime voice model cannot wait a
minute on a tool call), so bounded missions run as asyncio tasks. Each
mission can be polled or cancelled, and on completion an
announcement is handed to the voice layer, which speaks it.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any, Awaitable, Callable
from contextlib import asynccontextmanager
from collections import OrderedDict, deque
from jarvis.planner.resources import DesktopGate, WaitingCancelled, acquire

from jarvis.planner.engine import PlannerEngine, StepRecord, TaskOutcome


MAX_GOAL_LENGTH = 500

OnFinished = Callable[[str, TaskOutcome], Awaitable[None]]


class _SingleTask:
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
        self._id: str | None = None
        self._current_tool = None
        self.phase = "queued"
        self.read_only = False
        self.desktop_gate = None
        self.slots = None

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
        self._id = uuid.uuid4().hex
        self._cancel = threading.Event()
        self._steps = []
        self._current_tool = None
        self._outcome = None
        self._started = self.clock()
        self._task = asyncio.get_running_loop().create_task(self._run(self._goal, self._cancel))
        return {
            "ok": True,
            "task_started": True,
            "task_id": self._id,
            "message": (
                "Tache lancee en arriere-plan. Dis simplement a l'utilisateur que "
                "tu t'en occupes ; le resultat sera annonce a la fin."
            ),
        }

    def status(self) -> dict[str, Any]:
        if self.running and self._outcome is None:
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

    def progress(self) -> dict[str, Any] | None:
        """Presentation snapshot: no goal, arguments, result text or approval token."""
        if self._id is None:
            return None
        status = self._outcome.status if self._outcome is not None else (
            ("cancelling" if self._cancel.is_set() else self.phase) if self.running else "unknown")
        return {"id": self._id, "status": status,
                "steps": [step.to_dict() for step in self._steps],
                "step_count": len(self._steps)}

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

    def presentation(self) -> dict[str, Any] | None:
        """Desktop-only mission objective; no tool arguments or model summary.

        Unlike progress(), this deliberately exposes the task objective for
        the local session card. Never journal or persist this snapshot.
        """
        snapshot = self.progress()
        if snapshot is not None:
            snapshot.update(objective=self._goal, current_tool=self._current_tool, read_only=self.read_only)
        return snapshot

    def _action_changed(self, name):
        self._current_tool = name

    async def wait(self) -> TaskOutcome | None:
        """Await the current task (tests and shutdown)."""
        if self._task is not None:
            await asyncio.shield(self._task)
        return self._outcome

    @asynccontextmanager
    async def resources(self, cancel):
        if self.desktop_gate is None:
            yield
            return
        if self.read_only:
            async with acquire(self.slots, cancel):
                yield
        else:
            async with self.desktop_gate.hold(cancel):
                async with acquire(self.slots, cancel):
                    yield

    async def _run(self, goal: str, cancel: threading.Event) -> None:
        try:
            async with self.resources(cancel):
                if cancel.is_set():
                    raise WaitingCancelled()
                self.phase = "running"
                engine = self.engine_factory()
                if self.read_only:
                    if not isinstance(engine, PlannerEngine):
                        raise ValueError("Research requires a restricted planner")
                    engine.tools = {name: tool for name, tool in engine.tools.items() if name in RESEARCH_TOOLS}
                    engine.schemas = [schema for schema in engine.schemas if schema["function"]["name"] in RESEARCH_TOOLS | {"ask_clarification"}]
                if isinstance(engine, PlannerEngine):
                    engine.on_action = self._action_changed
                outcome = await engine.run(goal, cancel, on_step=self._steps.append)
        except WaitingCancelled:
            outcome = TaskOutcome("cancelled", "Mission annulee avant son execution.", list(self._steps))
        except Exception as error:
            outcome = TaskOutcome("failed", f"Erreur interne de la tache : {error}", list(self._steps))
        self._outcome = outcome
        self._current_tool = None
        if self.on_finished is not None:
            try:
                await self.on_finished(goal, outcome)
            except Exception:
                pass


# Strict subset of the planner allowlist. No browser, clipboard, capture,
# filesystem mutation, UI inspection, keyboard, mouse or message preparation.
RESEARCH_TOOLS = frozenset({"web_answer", "recall", "recent_activity", "list_files", "find_files", "get_file_info", "get_volume", "is_app_running", "get_media_state"})
ACTIVE_STATES = {"queued", "running", "cancelling"}


class TaskManager(_SingleTask):
    """Two running missions, up to six live requests, bounded session history.

    Default missions hold the shared desktop lease for their entire plan.
    Research missions are restricted by executable tool allowlist, not a prompt.
    """
    def __init__(self, engine_factory, on_finished=None, clock=None, desktop_gate=None):
        super().__init__(engine_factory, on_finished, clock)
        self.missions = OrderedDict()
        self.completed_order = deque(maxlen=10)
        self.desktop_gate = desktop_gate or DesktopGate()
        self.slots = asyncio.Semaphore(2)
        self.stopping = False

    @property
    def running(self):
        return any(mission.running and mission._outcome is None for mission in self.missions.values())

    def start(self, goal, read_only=False):
        if self.stopping:
            return {"ok": False, "error_code": "session_stopping", "message": "La session se ferme."}
        if not isinstance(read_only, bool):
            return {"ok": False, "error_code": "invalid_mode", "message": "Mode de mission invalide."}
        if sum(m.running for m in self.missions.values()) >= 6:
            return {"ok": False, "error_code": "task_queue_full", "message": "Six missions sont deja en cours ou en attente."}
        async def finished(goal, outcome):
            self.completed_order.append(mission._id)
            if self.on_finished is not None:
                await self.on_finished(goal, outcome)
        mission = _SingleTask(self.engine_factory, finished, self.clock)
        mission.read_only = read_only
        mission.desktop_gate, mission.slots = self.desktop_gate, self.slots
        result = mission.start(goal)
        if not result.get("ok"):
            return result
        self.missions[mission._id] = mission
        self._task = mission._task  # compatibility for integrations awaiting the latest launch
        while len(self.missions) > 10:
            oldest = next((key for key, item in self.missions.items() if not item.running), None)
            if oldest is None:
                break
            del self.missions[oldest]
        return result

    def _primary(self):
        return next((m for m in self.missions.values() if m.running and m._outcome is None), next(reversed(self.missions.values()), None))

    def status(self, task_id=None):
        if task_id is not None:
            mission = self.missions.get(task_id)
            if mission is None:
                return {"ok": False, "error_code": "task_not_found", "message": "Mission introuvable dans cette session."}
            return {**mission.status(), "task_id": task_id, "state": mission.progress()["status"]}
        if len(self.missions) > 1:
            return {"ok": True, "running": self.running, "tasks": [self.status(key) for key in self.missions]}
        primary = self._primary()
        return self.status(primary._id) if primary else super().status()

    def cancel(self, task_id=None):
        if task_id is not None:
            mission = self.missions.get(task_id)
            if mission is None:
                return {"ok": False, "error_code": "task_not_found", "message": "Mission introuvable dans cette session."}
            return {**mission.cancel(), "task_id": task_id}
        active = [m for m in self.missions.values() if m.running and m._outcome is None]
        if len(active) > 1:
            return {"ok": False, "error_code": "ambiguous_task", "message": "Plusieurs missions sont actives. Demande laquelle annuler puis utilise son task_id.", "tasks": [{"task_id": m._id, "goal": m._goal} for m in active]}
        return active[0].cancel() if active else {"ok": True, "cancel_requested": False, "message": "Aucune tache en cours a annuler."}

    def cancel_all(self):
        self.stopping = True
        for mission in self.missions.values():
            mission.cancel()

    def progress(self):
        primary = self._primary()
        return primary.progress() if primary else None

    def presentation(self):
        primary = self._primary()
        return primary.presentation() if primary else None

    def presentations(self):
        return [mission.presentation() for mission in self.missions.values()]

    async def wait(self):
        missions = list(self.missions.values())
        if missions:
            await asyncio.gather(*(m.wait() for m in missions))
            return missions[-1]._outcome
        return None

    def last_completed(self):
        for identifier in reversed(self.completed_order):
            mission = self.missions.get(identifier)
            if mission is None:
                continue
            result = mission.last_completed()
            if result is not None:
                return result
        return super().last_completed()


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
    if outcome.status == "needs_clarification":
        question = (outcome.pending or {}).get("question") or outcome.summary
        return (
            "La tache en arriere-plan a besoin d'une precision pour continuer. "
            f"Pose cette question a l'utilisateur, simplement : « {question} » "
            "Quand il repond, relance la tache avec cette information (run_task)."
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


