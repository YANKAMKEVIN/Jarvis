"""Runtime services of the Live tool registry."""
import asyncio
import functools
import inspect
import uuid
from typing import Any, Callable

from jarvis.activity import default_store as default_activity_store
from jarvis.capabilities.knowledge import web_announcement_for
from jarvis.capabilities.results import ToolResult
from jarvis.live.productivity import checklist_store
from jarvis.live.registry_base import RegistryCapabilities
from jarvis.planner.engine import TaskOutcome
from jarvis.planner.resources import DesktopGate
from jarvis.planner.tasks import announcement_for


class RegistryRuntime(RegistryCapabilities):
    """Session runtime shared by the tools: observers, journal, desktop gate,
    background web search and briefing, data purge and shutdown."""

    async def aclose(self):
        """Stop session-owned background work cooperatively before shutdown."""
        self.task_notifier = None
        if hasattr(self, "timers"):
            await self.timers.aclose()
        if self.tasks is not None:
            self.tasks.cancel_all()
        pending = [task for task in (self._web_task, self._briefing_task)
                   if task is not None and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if self.tasks is not None:
            await self.tasks.wait()
        if hasattr(self, "mcp_hub"):
            await self.mcp_hub.aclose()

    def set_presentation_observer(self, observer) -> None:
        self.presentation_observer = observer

    def set_activity_observer(self, observer) -> None:
        """Optional in-memory consumer; observer failures never affect a tool."""
        self.activity_observer = observer

    def _activity(self, event) -> None:
        observer = getattr(self, "activity_observer", None)
        if observer is not None:
            try:
                observer(event)
            except Exception:
                pass

    def set_task_notifier(self, notifier) -> None:
        self.task_notifier = notifier

    def note_user_turn(self) -> None:
        """The user spoke or typed: prepared actions may now be confirmed."""
        self.pending_actions.note_user_turn()

    async def _on_task_finished(self, goal: str, outcome: TaskOutcome) -> None:
        await self._log_action(f"task_{outcome.status}", None,
                               {"ok": outcome.status in ("completed", "needs_confirmation")})
        # Mission history survives a restart (the live task does not): objective
        # and final status only, so the user can review past missions later.
        steps = getattr(outcome, "steps", None)
        await asyncio.get_running_loop().run_in_executor(
            None, self.memory.log_mission, goal, outcome.status,
            len(steps) if isinstance(steps, list) else 0,
        )
        if not hasattr(self, "task_announcement_lock"):
            self.task_announcement_lock = asyncio.Lock()
        async with self.task_announcement_lock:
            if self.task_notifier is not None:
                await self.task_notifier(f"Concernant la mission « {goal} » : " + announcement_for(goal, outcome))

    def _desktop_access(self, fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if not hasattr(self, "desktop_gate"):
                self.desktop_gate = DesktopGate()
            gate = self.desktop_gate
            if not gate.owned and gate.busy:
                return {"ok": False, "error_code": "desktop_busy",
                        "message": "Une mission utilise le bureau. Attends sa fin ou demande quelle mission annuler. Aucune action n'a ete lancee."}
            async with gate.hold():
                return await fn(*args, **kwargs)
        return wrapper


    def _purge_personal_data(self, scope: str) -> ToolResult:
        counts: dict[str, int] = {}
        if scope in ("context", "all"):
            counts["context"] = self.context_store.clear()
        if scope in ("reminders", "all"):
            counts["reminders"] = self.reminder_store.purge_pending()
        if scope in ("scheduled", "all"):
            counts["scheduled"] = self.schedule_store.purge_pending()
        if scope in ("checklists", "all"):
            counts["checklists"] = checklist_store(self).clear()
        if scope in ("missions", "all"):
            counts["missions"] = self.memory.clear_missions()
        if scope in ("activity", "all"):
            counts["activity"] = default_activity_store().clear()
        total = sum(counts.values())
        return ToolResult.success(
            action="clear_personal_data",
            message=f"{total} element(s) efface(s) ({', '.join(f'{k}: {v}' for k, v in counts.items())}).",
            cleared=counts,
            total_cleared=total,
        )

    def _web_running(self) -> bool:
        return self._web_task is not None and not self._web_task.done()

    async def _run_web_search(self, question: str) -> None:
        try:
            result = await asyncio.to_thread(self.knowledge.answer, question)
        except Exception as error:
            result = ToolResult.failure(
                action="web_answer",
                message=f"La recherche web a echoue : {error}",
                error_code="system_error",
            )
        self._activity({"phase": "result", "tool": "search_the_web",
                        "id": "background:web", "result": result.to_livekit_dict()})
        # Keep the answer verbatim so the user can ask to send it afterwards.
        if result.ok and result.data.get("external_knowledge_retrieved"):
            self._last_web_result_text = self._format_web_result_for_send(result)
        else:
            self._last_web_result_text = None
        # Journal the outcome only (never the question or the content).
        await self._log_action("search_the_web", None, result)
        if self.task_notifier is not None:
            await self.task_notifier(web_announcement_for(result))

    def _briefing_running(self) -> bool:
        return self._briefing_task is not None and not self._briefing_task.done()

    async def _run_briefing(self, topic: str | None) -> None:
        from datetime import datetime

        date_label = datetime.now().strftime("%A %d %B %Y")

        # Agenda (best effort: a slow/locked calendar must not block the briefing).
        try:
            agenda = await asyncio.to_thread(self.calendar.list_today, 0)
        except Exception:
            agenda = None
        if agenda is not None and agenda.ok:
            count = agenda.data.get("event_count", 0)
            agenda_line = (
                f"{count} evenement(s) a l'agenda aujourd'hui" if count
                else "aucun evenement a l'agenda aujourd'hui"
            )
        else:
            agenda_line = "agenda non disponible"

        # News (reliable). With no explicit topic, apply a learned preference
        # ("actualites" -> e.g. "tech") locally if the user has set one.
        if isinstance(topic, str) and topic.strip():
            question = topic.strip()
        else:
            async with self.memory_lock:
                preferred = await asyncio.to_thread(self.memory.preferred, "actualites")
            question = (
                f"principales actualites {preferred} aujourd'hui" if preferred
                else "principales actualites importantes aujourd'hui"
            )
        try:
            news = await asyncio.to_thread(self.knowledge.answer, question)
            news_text = news.message if news.ok else ""
        except Exception:
            news_text = ""

        await self._log_action("morning_briefing", None, ToolResult.success(
            action="morning_briefing", message="ok"))
        if self.task_notifier is None:
            return
        announcement = (
            "Le briefing est pret. Transmets-le a l'utilisateur de maniere naturelle "
            f"et concise, sans lire d'URL : nous sommes {date_label} ; {agenda_line}. "
            f"Actualites : {news_text or 'non disponibles pour le moment'}. "
            "Termine en proposant d'aller plus loin sur un point si utile."
        )
        await self.task_notifier(announcement)

    @staticmethod
    def _format_web_result_for_send(result: ToolResult) -> str:
        """The web answer plus a couple of source links, for sending as text."""
        message = (result.message or "").strip()
        sources = result.data.get("sources") or []
        urls = [s.get("url") for s in sources[:2] if isinstance(s, dict) and s.get("url")]
        if urls:
            message = message + "\n\nSources :\n" + "\n".join(f"- {url}" for url in urls)
        return message

    async def _preferred_media_app(self) -> str | None:
        # Memory applied locally: the model never sees the preference.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.memory.preferred_media_app)

    async def _log_action(self, tool_name: str, target: str | None, result) -> None:
        # Off the event loop, but kept apart from asyncio.to_thread which is
        # reserved for capability calls.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self.memory.log_action, tool_name, target, result,
        )

    def _journaled(
        self,
        tool_name: str,
        target_arg: str | None = None,
        target_from: Callable[[Any], str | None] | None = None,
    ):
        """Record the action in the activity journal after it ran.

        Only the tool name, a non-sensitive target (app name, URL host) and
        the outcome are kept; never text, message content or paths.
        """
        def decorate(fn):
            signature = inspect.signature(fn)

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                activity_id = uuid.uuid4().hex
                self._activity({"phase": "started", "tool": tool_name, "id": activity_id})
                try:
                    result = await fn(*args, **kwargs)
                except BaseException as error:
                    phase = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
                    self._activity({"phase": phase, "tool": tool_name, "id": activity_id})
                    raise
                self._activity({"phase": "result", "tool": tool_name,
                                "id": activity_id, "result": result})
                target = None
                if target_arg is not None:
                    try:
                        value = signature.bind_partial(*args, **kwargs).arguments.get(target_arg)
                        target = target_from(value) if target_from else value
                    except Exception:
                        target = None
                await self._log_action(
                    tool_name,
                    target if isinstance(target, str) else None,
                    result,
                )
                return result

            return wrapper

        return decorate
