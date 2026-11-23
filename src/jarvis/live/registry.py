import asyncio
from jarvis.planner.resources import DesktopGate
from jarvis.activity import default_store as default_activity_store, log_event
from jarvis.live.productivity import productivity_tools, checklist_store
from jarvis.live.extensions import extension_tools
import functools
import inspect
import uuid
from typing import Any, Callable

from livekit.agents import function_tool

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.audio import AudioCapability
from jarvis.capabilities.browser import BrowserCapability
from jarvis.capabilities.calendar import CalendarCapability
from jarvis.capabilities.clipboard import ClipboardCapability
from jarvis.capabilities.compute import ComputeCapability
from jarvis.capabilities.diagnostics import DiagnosticsCapability
from jarvis.capabilities.document import DocumentCapability
from jarvis.capabilities.files import FilesCapability
from jarvis.capabilities.interaction import InteractionCapability
from jarvis.capabilities.keyboard import KeyboardCapability
from jarvis.capabilities.knowledge import KnowledgeCapability, web_announcement_for
from jarvis.capabilities.mail import MailCapability
from jarvis.capabilities.media import MediaCapability
from jarvis.capabilities.claude_sessions import ClaudeSessionsCapability
from jarvis.capabilities.memory import MemoryCapability
from jarvis.capabilities.system_metrics import SystemMetricsCapability
from jarvis.capabilities.usage import UsageCapability
from jarvis.capabilities.insights import InsightsCapability
from jarvis.capabilities.camera import CameraCapability
from jarvis.insights.detector import InsightDetector
from jarvis.capabilities.messaging import MessagingCapability
from jarvis.capabilities.mouse import MouseCapability
from jarvis.capabilities.notes import NotesCapability
from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.screenshot import ScreenshotCapability
from jarvis.capabilities.shortcuts import ShortcutsCapability
from jarvis.capabilities.system import SystemCapability
from jarvis.capabilities.text_workshop import TextWorkshopCapability
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.capabilities.vision import VisionCapability
from jarvis.capabilities.webread import WebReadCapability
from jarvis.capabilities.windows import WindowCapability
from jarvis.live.config import debug_live, get_vision_model, is_vision_enabled
from jarvis.context_store import ContextStore
from jarvis.live.confirmation import PendingActionStore
from jarvis.macros import MacroStore
from jarvis.planner.engine import PlannerEngine, TaskOutcome
from jarvis.planner.models import build_planner_model
from jarvis.planner.tasks import TaskManager, announcement_for
from jarvis.schedule.reminders import ReminderStore
from jarvis.schedule.store import ScheduledMessageStore
from jarvis.tools.vision import VisionTools


# Assistant apps whose input field is not introspectable via Accessibility
# (Electron/web, e.g. Claude): send_prompt_to_app types directly into the
# frontmost app instead of verifying an AX field. Low-risk prompt apps only;
# outward messaging never uses this path.
DIRECT_PROMPT_APPS = {"claude"}


# Tools allowed while the session is in safe (read-only) mode. The posture is
# DEFAULT-DENY: anything not listed here is refused when read_only_mode is on,
# so a tool added later is blocked in safe mode until it is deliberately
# cleared. The allowed set is reads/observations, Jarvis's own private stores
# (notes, checklists, memory, local reminders — never outward, never touching
# the Mac), safe stops, and the safe-mode switch itself (so there is always a
# way back out). Everything that changes the Mac or sends anything outward
# (apps, windows, files, clipboard, keyboard/mouse, mail, calendar, messaging,
# browser navigation, action confirmation, data erase, action replay) is
# blocked.
SAFE_MODE_ALLOWED = frozenset({
    "dance_avatar",
    # The safe-mode switch itself — never blocked, above all the way out.
    "enable_safe_mode", "disable_safe_mode",
    # System and media reads.
    "get_volume", "get_media_state", "get_battery_status", "get_system_info",
    "get_storage_status", "get_brightness", "self_check", "is_app_running",
    "list_shortcuts", "calculate", "convert_units",
    # File and document reads (no mutation).
    "list_files", "find_files", "search_files_by_content", "get_file_info",
    "ask_about_document",
    # Window / UI / clipboard / pointer reads.
    "get_active_window", "get_clipboard_text", "get_mouse_position",
    "inspect_ui", "find_ui_elements",
    # Screen observation only.
    "capture_screen", "capture_region", "capture_window",
    "describe_screen", "ask_about_screen", "describe_camera",
    # Calendar / mail / messaging reads.
    "list_calendar_events", "list_unread_emails", "summarize_unread_emails",
    "find_free_slots",
    "calendar_conflicts", "read_whatsapp_conversation",
    # Notes / checklists / document analysis (reads).
    "list_notes", "search_notes", "read_note",
    "compare_documents", "extract_document_actions",
    # Web knowledge (read only; nothing is sent).
    "search_the_web", "summarize_url", "morning_briefing", "web_answer",
    "browse_get_active_tab", "browse_list_tabs",
    # Jarvis's own private stores (local, never outward, never touch the Mac).
    "save_note", "append_note", "manage_checklist",
    "remember", "propose_memory", "forget", "recall", "list_memories",
    "remember_context", "recall_context",
    "set_reminder", "cancel_reminder", "list_reminders",
    "save_macro", "list_macros", "delete_macro", "save_task_procedure",
    # Token-usage introspection (reads the user's own local transcripts).
    "token_usage", "token_usage_by_model", "token_usage_by_project",
    "token_usage_trend", "compare_token_usage", "recent_claude_sessions",
    # Machine-activity introspection (live snapshot and local history).
    "system_snapshot", "top_processes", "system_usage_history", "check_anomalies",
    # Activity / privacy introspection and safe stops.
    "recent_activity", "recent_missions", "privacy_overview", "task_status",
    # Extensions: listing MCP tools and reading installed skills. Calling an
    # MCP tool (call_mcp_tool) stays blocked: its effect is unknown to Jarvis.
    "list_mcp_tools", "list_skills", "use_skill",
    "list_scheduled_messages", "cancel_scheduled_message", "list_timers",
    "cancel_action", "cancel_task", "pause_task", "resume_task",
    # Missions may still be launched: their own outward sub-actions run through
    # these same guarded tools, so they refuse too. A research (read_only)
    # mission stays fully useful.
    "run_task",
})


class ToolRegistry:
    def __init__(
        self,
        audio_capability=None,
        app_capability=None,
        media_capability=None,
        system_capability=None,
        window_capability=None,
        files_capability=None,
        clipboard_capability=None,
        keyboard_capability=None,
        mouse_capability=None,
        ui_accessibility_capability=None,
        interaction_capability=None,
        browser_capability=None,
        screenshot_capability=None,
        vision_capability=None,
        messaging_capability=None,
        memory_capability=None,
        knowledge_capability=None,
        schedule_store=None,
        reminder_store=None,
        text_workshop_capability=None,
        calendar_capability=None,
        mail_capability=None,
        usage_capability=None,
        system_metrics_capability=None,
        insights_capability=None,
        camera_capability=None,
        claude_sessions_capability=None,
        document_capability=None,
        macro_store=None,
        context_store=None,
        pending_actions=None,
        planner_model=None,
        scheduler_agent_missing=None,
    ):
        self.audio = (
            audio_capability
            if audio_capability is not None
            else AudioCapability()
        )
        self.apps = (
            app_capability
            if app_capability is not None
            else AppCapability()
        )
        self.media = (
            media_capability
            if media_capability is not None
            else MediaCapability()
        )
        self.system = (
            system_capability
            if system_capability is not None
            else SystemCapability()
        )
        self.windows = (
            window_capability
            if window_capability is not None
            else WindowCapability()
        )
        self.files = (
            files_capability
            if files_capability is not None
            else FilesCapability()
        )
        self.clipboard = (
            clipboard_capability
            if clipboard_capability is not None
            else ClipboardCapability()
        )
        self.keyboard = (
            keyboard_capability
            if keyboard_capability is not None
            else KeyboardCapability()
        )
        self.mouse = (
            mouse_capability
            if mouse_capability is not None
            else MouseCapability()
        )
        self.ui_accessibility = (
            ui_accessibility_capability
            if ui_accessibility_capability is not None
            else UIAccessibilityCapability()
        )
        self.interaction = (
            interaction_capability
            if interaction_capability is not None
            else InteractionCapability(
                apps=self.apps,
                windows=self.windows,
                ui_accessibility=self.ui_accessibility,
                keyboard=self.keyboard,
                clipboard=self.clipboard,
            )
        )
        self.browser = (
            browser_capability
            if browser_capability is not None
            else BrowserCapability()
        )
        self.screenshot = (
            screenshot_capability
            if screenshot_capability is not None
            else ScreenshotCapability()
        )
        self.vision = (
            vision_capability
            if vision_capability is not None
            else VisionCapability()
        )
        self.messaging = (
            messaging_capability
            if messaging_capability is not None
            else MessagingCapability()
        )
        self.memory = (
            memory_capability
            if memory_capability is not None
            else MemoryCapability()
        )
        self.knowledge = (
            knowledge_capability
            if knowledge_capability is not None
            else self._default_knowledge()
        )
        self.schedule_store = (
            schedule_store
            if schedule_store is not None
            else ScheduledMessageStore()
        )
        self.reminder_store = (
            reminder_store
            if reminder_store is not None
            else ReminderStore()
        )
        self.text_workshop = (
            text_workshop_capability
            if text_workshop_capability is not None
            else TextWorkshopCapability(self.clipboard, model=planner_model)
        )
        self.calendar = (
            calendar_capability
            if calendar_capability is not None
            else CalendarCapability()
        )
        self.mail = (
            mail_capability
            if mail_capability is not None
            else MailCapability(model=planner_model)
        )
        self.usage = (
            usage_capability
            if usage_capability is not None
            else UsageCapability()
        )
        self.system_metrics = (
            system_metrics_capability
            if system_metrics_capability is not None
            else SystemMetricsCapability()
        )
        self.insights = (
            insights_capability
            if insights_capability is not None
            else InsightsCapability(InsightDetector(
                metrics=self.system_metrics.store, usage=self.usage.store,
                probe=self.system_metrics.probe))
        )
        self.camera = (
            camera_capability
            if camera_capability is not None
            else CameraCapability(vision_tools=getattr(self.vision, "vision_tools", None))
        )
        self.claude_sessions = (
            claude_sessions_capability
            if claude_sessions_capability is not None
            else ClaudeSessionsCapability()
        )
        self.compute = ComputeCapability()
        self.notes = NotesCapability()
        self.diagnostics = DiagnosticsCapability()
        self.shortcuts = ShortcutsCapability()
        self.macro_store = macro_store if macro_store is not None else MacroStore()
        self.context_store = context_store if context_store is not None else ContextStore()
        self.webread = WebReadCapability(model=planner_model)
        self.document = (
            document_capability
            if document_capability is not None
            else DocumentCapability(self.files.filesystem_tools, model=planner_model)
        )
        if scheduler_agent_missing is None:
            from jarvis.schedule.agent import scheduler_agent_missing
        self.scheduler_agent_missing = scheduler_agent_missing
        self.pending_actions = (
            pending_actions
            if pending_actions is not None
            else PendingActionStore()
        )
        self.media_lock = asyncio.Lock()
        self.clipboard_lock = asyncio.Lock()
        self.keyboard_lock = asyncio.Lock()
        self.mouse_lock = asyncio.Lock()
        self.ui_lock = asyncio.Lock()
        self.interaction_lock = asyncio.Lock()
        self.browser_lock = asyncio.Lock()
        self.screenshot_lock = asyncio.Lock()
        self.vision_lock = asyncio.Lock()
        self.confirmation_lock = asyncio.Lock()
        self.memory_lock = asyncio.Lock()
        # Brain of background tasks; local Ollama unless injected (tests).
        self.planner_model = planner_model
        # Set by the voice agent: async callable speaking an announcement.
        self.task_notifier = None
        self.tasks: TaskManager | None = None
        # The planner's tool set (voice tools + planner-only web_answer); filled
        # by livekit_tools().
        self.planner_tools: list[Any] = []
        # Single-shot web search runs in the background so the voice model can
        # acknowledge at once and announce the result when it lands.
        self._web_task: asyncio.Task | None = None
        # The last retrieved web answer, kept verbatim so "envoie ça" sends
        # exactly what was found (not a paraphrase). Content only; never logged.
        self._last_web_result_text: str | None = None
        # Morning briefing runs in the background like a web search.
        self._briefing_task: asyncio.Task | None = None
        self.activity_observer = None
        self.presentation_observer = None
        self.desktop_gate = DesktopGate()
        self.task_announcement_lock = asyncio.Lock()
        # Session-scoped safe mode: when True, only SAFE_MODE_ALLOWED tools run;
        # every outward or system-mutating tool refuses without side effect.
        # Defaults off and does not persist across restarts (see docs).
        self.read_only_mode = False

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

    @staticmethod
    def _default_knowledge() -> KnowledgeCapability:
        # Free and local: a running SearXNG if present, else keyless web search
        # (Google News RSS / DuckDuckGo). Synthesis uses the local Ollama brain.
        # Imported lazily so the registry stays light for callers that inject.
        from jarvis.brain import LocalBrain
        from jarvis.knowledge.keyless import FallbackProvider, KeylessWebProvider
        from jarvis.knowledge.searxng import SearXNGProvider
        from jarvis.knowledge.service import KnowledgeService

        provider = FallbackProvider(SearXNGProvider(), KeylessWebProvider())
        return KnowledgeCapability(KnowledgeService(brain=LocalBrain(), provider=provider))

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

    def _scheduler_agent_warning(self) -> dict:
        """Extra result fields when the launchd delivery agent is missing."""
        try:
            missing = bool(self.scheduler_agent_missing())
        except Exception:
            missing = False
        if not missing:
            return {}
        from jarvis.schedule.agent import MISSING_MESSAGE
        return {"scheduler_agent_missing": True, "warning": MISSING_MESSAGE}

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

    def _guard_read_only(self, tool):
        """Return a copy of a voice/planner tool that refuses in safe mode.

        Single enforcement point for safe (read-only) mode. A tool whose name
        is in SAFE_MODE_ALLOWED is returned unchanged; any other tool is wrapped
        so that, while self.read_only_mode is on, it refuses with no side effect
        and nothing sent. The wrapper keeps the original name, description and
        signature, so the schema the model sees is identical — the model simply
        gets a refusal result if it calls a blocked tool in safe mode. The flag
        is read live, so entering safe mode also stops a mission's outward
        sub-actions already in flight (they share these guarded tools).

        Every call is also logged by name (never its arguments) to the local
        activity journal behind the dashboard's Jarvis tab.
        """
        name = tool.info.name
        allowed = name in SAFE_MODE_ALLOWED
        inner = tool._func

        @functools.wraps(inner)
        async def wrapper(*args, **kwargs):
            log_event("tool", name)
            if not allowed and getattr(self, "read_only_mode", False):
                return ToolResult.failure(
                    action=name,
                    message=(
                        "Mode securite actif (lecture seule) : cette action "
                        "modifierait le Mac ou enverrait quelque chose vers "
                        "l'exterieur, donc elle est bloquee et rien n'a ete fait. "
                        "Dis « quitte le mode securite » pour la reactiver."
                    ),
                    error_code="read_only_mode",
                ).to_livekit_dict()
            return await inner(*args, **kwargs)

        return function_tool(name=name, description=tool.info.description)(wrapper)

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

    def livekit_tools(self) -> list[Any]:
        # One module per tool family (live/tools_*.py); each returns its tools by name.
        from jarvis.live.tools_system import system_tools
        from jarvis.live.tools_office import office_tools
        from jarvis.live.tools_insights import insights_tools
        from jarvis.live.tools_windows import windows_tools
        from jarvis.live.tools_files import files_tools
        from jarvis.live.tools_input import input_tools
        from jarvis.live.tools_messages import messages_tools
        from jarvis.live.tools_memory import memory_tools
        from jarvis.live.tools_web import web_tools
        from jarvis.live.tools_missions import missions_tools
        from jarvis.live.tools_schedule import schedule_tools
        from jarvis.live.tools_privacy import privacy_tools
        t: dict[str, Any] = {}
        for family in (system_tools, office_tools, insights_tools, windows_tools, files_tools, input_tools, messages_tools, memory_tools, web_tools, missions_tools, schedule_tools, privacy_tools):
            t.update(family(self))

        tools = [
            t["enable_safe_mode"],
            t["disable_safe_mode"],
            t["set_volume"],
            t["get_volume"],
            t["open_app"],
            t["close_app"],
            t["is_app_running"],
            t["play_pause"],
            t["next_track"],
            t["previous_track"],
            t["get_media_state"],
            t["get_battery_status"],
            t["get_storage_status"],
            t["get_system_info"],
            t["self_check"],
            t["run_shortcut"],
            t["list_shortcuts"],
            t["calculate"],
            t["convert_units"],
            t["save_note"],
            t["list_notes"],
            t["list_calendar_events"],
            t["create_calendar_event"],
            t["list_unread_emails"],
            t["summarize_unread_emails"],
            t["token_usage"],
            t["token_usage_by_model"],
            t["token_usage_by_project"],
            t["token_usage_trend"],
            t["compare_token_usage"],
            t["recent_claude_sessions"],
            t["system_snapshot"],
            t["top_processes"],
            t["system_usage_history"],
            t["check_anomalies"],
            t["run_claude_task"],
            t["open_claude_session"],
            t["draft_email"],
            t["get_brightness"],
            t["set_brightness"],
            t["lock_screen"],
            t["get_active_window"],
            t["focus_window"],
            t["minimize_window"],
            t["maximize_window"],
            t["move_window"],
            t["arrange_windows"],
            t["list_files"],
            t["find_files"],
            t["search_files_by_content"],
            t["get_file_info"],
            t["open_file"],
            t["open_folder"],
            t["create_folder"],
            t["rename_file"],
            t["move_file"],
            t["get_clipboard_text"],
            t["set_clipboard_text"],
            t["clear_clipboard"],
            t["rewrite_clipboard"],
            t["type_text"],
            t["press_key"],
            t["hotkey"],
            t["get_mouse_position"],
            t["move_mouse"],
            t["click"],
            t["click_element"],
            t["double_click"],
            t["right_click"],
            t["scroll"],
            t["inspect_ui"],
            t["find_ui_elements"],
            t["focus_ui_element"],
            t["activate_ui_element"],
            t["select_all_and_copy"],
            t["focus_app_ui_and_type"],
            t["open_app_and_focus_ui"],
            t["select_all_and_delete"],
            t["send_prompt_to_app"],
            t["prepare_send_message"],
            t["confirm_action"],
            t["cancel_action"],
            t["remember"],
            t["propose_memory"],
            t["recall"],
            t["list_memories"],
            t["forget"],
            t["recent_activity"],
            t["recent_missions"],
            t["browse_open_url"],
            t["browse_search_web"],
            t["browse_get_active_tab"],
            t["browse_list_tabs"],
            t["browse_activate_tab"],
            t["capture_screen"],
            t["capture_region"],
            t["capture_window"],
            t["describe_screen"],
            t["ask_about_screen"],
            t["describe_camera"],
            t["ask_about_document"],
            t["read_whatsapp_conversation"],
            t["search_the_web"],
            t["summarize_url"],
            t["morning_briefing"],
            t["send_last_web_result"],
            t["schedule_message"],
            t["list_scheduled_messages"],
            t["cancel_scheduled_message"],
            t["set_reminder"],
            t["list_reminders"],
            t["cancel_reminder"],
            t["privacy_overview"],
            t["run_task"],
            t["task_status"],
            t["cancel_task"],
            t["save_task_procedure"],
            t["run_procedure"],
            t["save_macro"],
            t["run_macro"],
            t["list_macros"],
            t["delete_macro"],
            t["remember_context"],
            t["recall_context"],
            t["clear_personal_data"],
        ]

        tools.append(t["dance_avatar"])
        tools.extend(productivity_tools(self))
        tools.extend(extension_tools(self))

        # Single safe-mode enforcement point: every voice and planner tool is
        # routed through the read-only guard, so a mission cannot perform an
        # outward action in safe mode any more than the voice can.
        tools = [self._guard_read_only(tool) for tool in tools]

        # The planner drives these very tools (same locks, journal and pending
        # action store), so a message it prepares is confirmable by voice. It
        # also gets web_answer, a blocking web search kept out of the voice
        # tool set (the voice uses the background search_the_web instead).
        self.planner_tools = [tool for tool in tools if tool.info.name != "dance_avatar"] + [self._guard_read_only(t["web_answer"])]
        if not hasattr(self, "desktop_gate"):
            self.desktop_gate = DesktopGate()
        self.tasks = TaskManager(
            lambda: PlannerEngine(
                self.planner_model or build_planner_model(), self.planner_tools
            ),
            on_finished=self._on_task_finished,
            desktop_gate=self.desktop_gate,
        )
        return tools

    @staticmethod
    def _debug_tool_result(tool_name: str, result) -> None:
        if result.ok:
            debug_live(
                "tool_succeeded",
                tool=tool_name,
                app=result.data.get("app"),
                title=result.data.get("title"),
                playing=result.data.get("playing"),
            )
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_clipboard_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "has_text": result.data.get("has_text"),
            "length": result.data.get("length"),
            "returned_length": result.data.get("returned_length"),
            "truncated": result.data.get("truncated"),
            "content_type": result.data.get("content_type"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_keyboard_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "length": result.data.get("length"),
            "key": result.data.get("key"),
            "keys": result.data.get("keys"),
            "target_app": result.data.get("target_app"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_mouse_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "x": result.data.get("x"),
            "y": result.data.get("y"),
            "direction": result.data.get("direction"),
            "amount": result.data.get("amount"),
            "button": result.data.get("button"),
            "click_count": result.data.get("click_count"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_ui_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "count": result.data.get("count"),
            "truncated": result.data.get("truncated"),
            "role": result.data.get("role"),
            "query_length": result.data.get("query_length"),
            "candidate_count": result.data.get("candidate_count"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
            )

    @staticmethod
    def _debug_interaction_result(tool_name: str, result) -> None:
        fields = {
            "tool": tool_name,
            "target_app": result.data.get("target_app"),
            "query_length": result.data.get("query_length"),
            "text_length": result.data.get("text_length"),
            "press_enter": result.data.get("press_enter"),
            "failed_step": result.data.get("failed_step"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
            "step_count": len(result.data.get("steps", [])),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                error=result.error_code,
                failed_step=result.data.get("failed_step"),
            )

    @staticmethod
    def _debug_browser_result(tool_name: str, result) -> None:
        # Log host and counts only; never the full URL or page title.
        fields = {
            "tool": tool_name,
            "browser": result.data.get("browser"),
            "active_host": ToolRegistry._debug_host(result.data.get("active_url")),
            "has_window": result.data.get("has_window"),
            "tab_count": result.data.get("count"),
            "new_tab": result.data.get("new_tab"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live(
                "tool_failed",
                tool=tool_name,
                browser=result.data.get("browser"),
                error=result.error_code,
            )

    @staticmethod
    def _journal_host(url) -> str | None:
        """Bare host for the journal: no credentials, port, path or query."""
        if not isinstance(url, str) or not url.strip():
            return None

        from urllib.parse import urlparse

        text = url.strip()
        parsed = urlparse(text if "://" in text else f"//{text}")
        try:
            host = parsed.hostname
        except ValueError:
            return None
        if not host:
            return None
        return host[4:] if host.startswith("www.") else host

    @staticmethod
    def _debug_host(url) -> str | None:
        if not isinstance(url, str) or not url:
            return None

        from urllib.parse import urlparse

        return urlparse(url).netloc or None

    @staticmethod
    def _debug_screenshot_result(tool_name: str, result) -> None:
        # Log the file basename and metadata only, never the full path.
        import os as _os

        path = result.data.get("path")
        fields = {
            "tool": tool_name,
            "file": _os.path.basename(path) if isinstance(path, str) else None,
            "bytes": result.data.get("bytes"),
            "width": result.data.get("width"),
            "height": result.data.get("height"),
            "target_app": result.data.get("target_app"),
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live("tool_failed", tool=tool_name, error=result.error_code)

    def _messaging_check(self, name: str, app_name: str) -> bool:
        """Ask the messaging capability a per-app question (is_api_app,
        requires_recipient, supports_verified_send). A capability without the
        newer API-aware checks is treated as UI-only (composer send)."""
        check = getattr(self.messaging, name, None)
        if callable(check):
            return bool(check(app_name))
        if name == "supports_verified_send":
            return bool(self.messaging.supports_composer_send(app_name))
        return False

    @staticmethod
    def _vision_guard(tool_name: str) -> dict | None:
        # Opt-in gate: Vision sends a screen capture to an external service.
        if is_vision_enabled():
            return None

        debug_live("tool_failed", tool=tool_name, error="vision_disabled")
        return {
            "ok": False,
            "action": tool_name,
            "message": (
                "La vision est desactivee. Active JARVIS_VISION_ENABLED pour "
                "autoriser Jarvis a analyser une capture d'ecran."
            ),
            "error_code": "vision_disabled",
        }

    @staticmethod
    def _debug_vision_result(tool_name: str, result) -> None:
        # Metadata only: never the analysis text, the raw question, the image
        # bytes/base64, or the full path.
        import os as _os

        path = result.data.get("image_path")
        fields = {
            "tool": tool_name,
            "source": result.data.get("source"),
            "target_app": result.data.get("target_app"),
            "model": result.data.get("model"),
            "image_file": _os.path.basename(path) if isinstance(path, str) else None,
            "image_bytes": result.data.get("image_bytes"),
            "image_width": result.data.get("image_width"),
            "image_height": result.data.get("image_height"),
            "question_length": result.data.get("question_length"),
            "duration_ms": result.data.get("duration_ms"),
        }

        if result.ok:
            debug_live("tool_succeeded", **fields)
        else:
            debug_live("tool_failed", tool=tool_name, error=result.error_code)


def create_live_tools(*args, **kwargs) -> list[Any]:
    return create_live_registry(*args, **kwargs).livekit_tools()


def create_live_registry(
    security=None,
    macos_tools=None,
    filesystem_tools=None,
    clipboard_tools=None,
    keyboard_tools=None,
    mouse_tools=None,
    accessibility_tools=None,
    audio_capability=None,
    app_capability=None,
    media_capability=None,
    system_capability=None,
    window_capability=None,
    files_capability=None,
    clipboard_capability=None,
    keyboard_capability=None,
    mouse_capability=None,
    ui_accessibility_capability=None,
    interaction_capability=None,
    browser_capability=None,
    screenshot_capability=None,
    vision_capability=None,
    messaging_capability=None,
    memory_capability=None,
    knowledge_capability=None,
    schedule_store=None,
    reminder_store=None,
    text_workshop_capability=None,
    calendar_capability=None,
    mail_capability=None,
    usage_capability=None,
    system_metrics_capability=None,
    claude_sessions_capability=None,
    document_capability=None,
    macro_store=None,
    context_store=None,
    planner_model=None,
    scheduler_agent_missing=None,
) -> "ToolRegistry":
    if audio_capability is None:
        audio_capability = AudioCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if app_capability is None:
        app_capability = AppCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if media_capability is None:
        media_capability = MediaCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if system_capability is None:
        system_capability = SystemCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if window_capability is None:
        window_capability = WindowCapability(
            security=security,
            macos_tools=macos_tools,
        )

    if files_capability is None:
        files_capability = FilesCapability(
            security=security,
            filesystem_tools=filesystem_tools,
        )

    if clipboard_capability is None:
        clipboard_capability = ClipboardCapability(
            security=security,
            clipboard_tools=clipboard_tools,
        )

    if keyboard_capability is None:
        keyboard_capability = KeyboardCapability(
            security=security,
            keyboard_tools=keyboard_tools,
        )

    if mouse_capability is None:
        mouse_capability = MouseCapability(
            security=security,
            mouse_tools=mouse_tools,
        )

    if ui_accessibility_capability is None:
        ui_accessibility_capability = UIAccessibilityCapability(
            security=security,
            accessibility_tools=accessibility_tools,
        )

    if interaction_capability is None:
        interaction_capability = InteractionCapability(
            apps=app_capability,
            windows=window_capability,
            ui_accessibility=ui_accessibility_capability,
            keyboard=keyboard_capability,
            clipboard=clipboard_capability,
        )

    if browser_capability is None:
        browser_capability = BrowserCapability()

    if screenshot_capability is None:
        screenshot_capability = ScreenshotCapability(windows=window_capability)

    if vision_capability is None:
        vision_capability = VisionCapability(
            screenshot=screenshot_capability,
            vision_tools=VisionTools(model=get_vision_model()),
        )

    if messaging_capability is None:
        messaging_capability = MessagingCapability(
            windows=window_capability,
            ui_accessibility=ui_accessibility_capability,
            apps=app_capability,
            keyboard=keyboard_capability,
        )

    return ToolRegistry(
        audio_capability=audio_capability,
        app_capability=app_capability,
        media_capability=media_capability,
        system_capability=system_capability,
        window_capability=window_capability,
        files_capability=files_capability,
        clipboard_capability=clipboard_capability,
        keyboard_capability=keyboard_capability,
        mouse_capability=mouse_capability,
        ui_accessibility_capability=ui_accessibility_capability,
        interaction_capability=interaction_capability,
        browser_capability=browser_capability,
        screenshot_capability=screenshot_capability,
        vision_capability=vision_capability,
        messaging_capability=messaging_capability,
        memory_capability=memory_capability,
        knowledge_capability=knowledge_capability,
        schedule_store=schedule_store,
        reminder_store=reminder_store,
        text_workshop_capability=text_workshop_capability,
        calendar_capability=calendar_capability,
        mail_capability=mail_capability,
        usage_capability=usage_capability,
        system_metrics_capability=system_metrics_capability,
        claude_sessions_capability=claude_sessions_capability,
        document_capability=document_capability,
        macro_store=macro_store,
        context_store=context_store,
        planner_model=planner_model,
        scheduler_agent_missing=scheduler_agent_missing,
    )


