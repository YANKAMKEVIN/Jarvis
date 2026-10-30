import asyncio
from jarvis.planner.resources import DesktopGate
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
from jarvis.context_store import ContextError, ContextStore
from jarvis.live.confirmation import PendingActionStore
from jarvis.macros import MacroError, MacroStore
from jarvis.planner.engine import PlannerEngine, TaskOutcome
from jarvis.planner.models import build_planner_model
from jarvis.planner.tasks import TaskManager, announcement_for
from jarvis.schedule.reminders import ReminderError, ReminderStore
from jarvis.schedule.store import ScheduleError, ScheduledMessageStore, parse_due_at
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
    "describe_screen", "ask_about_screen",
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
    "list_scheduled_messages", "cancel_scheduled_message",
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
        claude_sessions_capability=None,
        document_capability=None,
        macro_store=None,
        context_store=None,
        pending_actions=None,
        planner_model=None,
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
        """
        name = tool.info.name
        if name in SAFE_MODE_ALLOWED:
            return tool
        inner = tool._func

        @functools.wraps(inner)
        async def wrapper(*args, **kwargs):
            if getattr(self, "read_only_mode", False):
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
        # The avatar on screen IS Jarvis: results are worded so the model says
        # "je danse", never that a command or request was sent to something else.
        @function_tool(name="dance_avatar", description="Te fait danser toi-même, Jarvis, à l'écran pendant huit secondes, quand l'utilisateur te demande de danser ou si tu sais danser. stop=True arrête ta danse, sans couper le vocal. Aucune musique. Si les animations sont réduites ou ton apparence est abstraite, l'écran l'indique.")
        async def dance_avatar(stop: bool = False) -> dict:
            observer = self.presentation_observer
            if observer is None:
                return {"ok": False, "error": "desktop_unavailable",
                        "message": "Tu ne peux pas danser ici : ton avatar n'est pas affiché. Dis-le simplement, à la première personne."}
            observer({"type": "avatar_dance", "action": "stop" if stop else "start"})
            if stop:
                return {"ok": True, "status": "stopped",
                        "message": "Tu t'arrêtes de danser. Dis-le en quelques mots, à la première personne."}
            return {"ok": True, "status": "dancing",
                    "message": "Tu danses maintenant, pendant huit secondes. Dis-le tout de suite à la première personne, avec une phrase courte et joueuse (« Et je danse ! »). Ne parle ni de commande, ni de demande, ni de compagnon."}

        @function_tool(
            name="set_volume",
            description=(
                "Modifie réellement le volume de sortie du Mac de l'utilisateur. "
                "Utilise ce tool quand l'utilisateur demande de mettre, régler, "
                "monter ou baisser le volume à un niveau précis entre 0 et 100."
            ),
        )
        @self._journaled("set_volume")
        async def set_volume(volume: int) -> dict:
            """Set the Mac output volume to a value between 0 and 100."""
            debug_live("tool_call", tool="set_volume", volume=volume)
            result = await asyncio.to_thread(self.audio.set_volume, volume)

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="set_volume",
                    volume=result.data.get("volume"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="set_volume",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="get_volume",
            description=(
                "Lit le volume de sortie actuel du Mac de l'utilisateur. "
                "Utilise ce tool quand l'utilisateur demande le volume actuel."
            ),
        )
        async def get_volume() -> dict:
            """Read the current Mac output volume."""
            debug_live("tool_call", tool="get_volume")
            result = await asyncio.to_thread(self.audio.get_volume)

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="get_volume",
                    volume=result.data.get("volume"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="get_volume",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="open_app",
            description=(
                "Ouvre réellement une application macOS par son nom exact. "
                "Utilise ce tool quand l'utilisateur demande d'ouvrir, lancer "
                "ou démarrer une application comme Safari, Spotify ou "
                "Visual Studio Code."
            ),
        )
        @self._journaled("open_app", "app_name")
        @self._desktop_access
        async def open_app(app_name: str) -> dict:
            """Open a macOS application by name."""
            debug_live("tool_call", tool="open_app", app_name=app_name)
            result = await asyncio.to_thread(self.apps.open_app, app_name)

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="open_app",
                    target=result.data.get("target"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="open_app",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="close_app",
            description=(
                "Ferme réellement une application macOS par son nom exact. "
                "Utilise ce tool quand l'utilisateur demande de fermer, "
                "quitter ou arrêter une application."
            ),
        )
        @self._journaled("close_app", "app_name")
        @self._desktop_access
        async def close_app(app_name: str) -> dict:
            """Close a macOS application by name."""
            debug_live("tool_call", tool="close_app", app_name=app_name)
            result = await asyncio.to_thread(self.apps.close_app, app_name)

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="close_app",
                    target=result.data.get("target"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="close_app",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="is_app_running",
            description=(
                "Vérifie si une application macOS est actuellement ouverte "
                "ou en cours d'exécution. Utilise ce tool quand l'utilisateur "
                "demande si une application est ouverte, lancée ou tourne."
            ),
        )
        async def is_app_running(app_name: str) -> dict:
            """Check whether a macOS application is currently running."""
            debug_live("tool_call", tool="is_app_running", app_name=app_name)
            result = await asyncio.to_thread(
                self.apps.is_app_running,
                app_name,
            )

            if result.ok:
                debug_live(
                    "tool_succeeded",
                    tool="is_app_running",
                    target=result.data.get("target"),
                    running=result.data.get("running"),
                )
            else:
                debug_live(
                    "tool_failed",
                    tool="is_app_running",
                    error=result.error_code,
                )

            return result.to_livekit_dict()

        @function_tool(
            name="play_pause",
            description=(
                "Met en pause ou reprend la lecture du média actif compatible "
                "sur le Mac. Utilise ce tool pour les demandes comme pause, "
                "reprends la lecture, play ou mets la musique en pause."
            ),
        )
        @self._journaled("play_pause")
        @self._desktop_access
        async def play_pause() -> dict:
            """Toggle play/pause for the active supported media app."""
            debug_live("tool_call", tool="play_pause")
            async with self.media_lock:
                # Inside the lock so concurrent media calls keep their order.
                preferred = await self._preferred_media_app()
                result = await (
                    asyncio.to_thread(self.media.play_pause, preferred)
                    if preferred
                    else asyncio.to_thread(self.media.play_pause)
                )
            self._debug_tool_result("play_pause", result)
            return result.to_livekit_dict()

        @function_tool(
            name="next_track",
            description=(
                "Passe au morceau suivant dans l'application média compatible "
                "active. Utilise ce tool quand l'utilisateur demande la "
                "suivante, le titre suivant ou de passer au prochain morceau."
            ),
        )
        @self._journaled("next_track")
        @self._desktop_access
        async def next_track() -> dict:
            """Skip to the next track in the active supported media app."""
            debug_live("tool_call", tool="next_track")
            async with self.media_lock:
                # Inside the lock so concurrent media calls keep their order.
                preferred = await self._preferred_media_app()
                result = await (
                    asyncio.to_thread(self.media.next_track, preferred)
                    if preferred
                    else asyncio.to_thread(self.media.next_track)
                )
            self._debug_tool_result("next_track", result)
            return result.to_livekit_dict()

        @function_tool(
            name="previous_track",
            description=(
                "Revient au morceau précédent dans l'application média "
                "compatible active. Utilise ce tool quand l'utilisateur "
                "demande la chanson précédente ou de revenir en arrière."
            ),
        )
        @self._journaled("previous_track")
        @self._desktop_access
        async def previous_track() -> dict:
            """Go back to the previous track in the active supported media app."""
            debug_live("tool_call", tool="previous_track")
            async with self.media_lock:
                # Inside the lock so concurrent media calls keep their order.
                preferred = await self._preferred_media_app()
                result = await (
                    asyncio.to_thread(self.media.previous_track, preferred)
                    if preferred
                    else asyncio.to_thread(self.media.previous_track)
                )
            self._debug_tool_result("previous_track", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_media_state",
            description=(
                "Lit l'état réel du média actif compatible sur le Mac. "
                "Utilise ce tool quand l'utilisateur demande ce qui joue, "
                "quel morceau est en cours ou si la lecture est active."
            ),
        )
        async def get_media_state() -> dict:
            """Read the current supported media playback state."""
            debug_live("tool_call", tool="get_media_state")
            async with self.media_lock:
                result = await asyncio.to_thread(self.media.get_media_state)
            self._debug_tool_result("get_media_state", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_battery_status",
            description=(
                "Lit l'etat reel de la batterie du Mac : pourcentage, charge "
                "en cours et alimentation secteur."
            ),
        )
        async def get_battery_status() -> dict:
            """Read the current Mac battery status."""
            debug_live("tool_call", tool="get_battery_status")
            result = await asyncio.to_thread(self.system.get_battery_status)
            self._debug_tool_result("get_battery_status", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_system_info",
            description=(
                "Lit les informations materielles reelles du Mac utilise, "
                "comme le modele, l'identifiant modele, la puce et la memoire."
            ),
        )
        async def get_system_info() -> dict:
            """Read current Mac hardware information."""
            debug_live("tool_call", tool="get_system_info")
            result = await asyncio.to_thread(self.system.get_system_info)
            self._debug_tool_result("get_system_info", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_storage_status",
            description=(
                "Lit l'espace disque reel du Mac (libre, utilise, total) et signale "
                "si l'espace est faible. Utilise ce tool pour 'combien de place il me "
                "reste', 'mon disque est-il plein'."
            ),
        )
        async def get_storage_status() -> dict:
            """Read current disk space."""
            debug_live("tool_call", tool="get_storage_status")
            result = await asyncio.to_thread(self.system.get_storage_status)
            self._debug_tool_result("get_storage_status", result)
            return result.to_livekit_dict()

        @function_tool(
            name="self_check",
            description=(
                "Diagnostic : indique quelles capacites et permissions sont "
                "disponibles (accessibilite, enregistrement d'ecran, vision, modele "
                "local Ollama, IMAP) et ce qui manque, avec une piste de correction. "
                "Pour 'fais un check', 'qu'est-ce qui fonctionne', 'tes permissions'."
            ),
        )
        async def self_check() -> dict:
            """Report available capabilities and permissions."""
            debug_live("tool_call", tool="self_check")
            result = await asyncio.to_thread(self.diagnostics.self_check)
            return result.to_livekit_dict()

        @function_tool(
            name="run_shortcut",
            description=(
                "Lance un Raccourci (Shortcuts) macOS par son nom : 'active Ne pas "
                "deranger', 'lance mon raccourci Focus travail'. C'est le moyen "
                "fiable d'activer des automatisations que l'utilisateur a creees "
                "(Focus/DND, luminosite, etc.). name : le nom exact du raccourci. "
                "Utilise list_shortcuts si tu n'es pas sur du nom."
            ),
        )
        @self._journaled("run_shortcut", "name")
        @self._desktop_access
        async def run_shortcut(name: str) -> dict:
            """Run a macOS Shortcut by name."""
            debug_live("tool_call", tool="run_shortcut")
            result = await asyncio.to_thread(self.shortcuts.run_shortcut, name)
            self._debug_tool_result("run_shortcut", result)
            return result.to_livekit_dict()

        @function_tool(
            name="list_shortcuts",
            description=(
                "Liste les Raccourcis (Shortcuts) macOS disponibles, par leur nom. "
                "Pour 'quels raccourcis j'ai', ou pour trouver le bon nom avant "
                "run_shortcut."
            ),
        )
        async def list_shortcuts() -> dict:
            """List available macOS Shortcuts."""
            debug_live("tool_call", tool="list_shortcuts")
            result = await asyncio.to_thread(self.shortcuts.list_shortcuts)
            self._debug_tool_result("list_shortcuts", result)
            return result.to_livekit_dict()

        @function_tool(
            name="calculate",
            description=(
                "Calcule une expression arithmetique en local (de maniere sure) : "
                "'combien font 15% de 240', '(12+8)*3', 'racine de 2'. expression : "
                "l'expression mathematique (nombres, + - * / %, puissance **, "
                "parentheses, fonctions sqrt/log/sin/cos/min/max, constantes pi/e)."
            ),
        )
        async def calculate(expression: str) -> dict:
            """Evaluate a safe arithmetic expression locally."""
            debug_live("tool_call", tool="calculate")
            result = await asyncio.to_thread(self.compute.calculate, expression)
            self._debug_tool_result("calculate", result)
            return result.to_livekit_dict()

        @function_tool(
            name="convert_units",
            description=(
                "Convertit une valeur entre unites (longueur, masse, volume, "
                "temperature) en local : 'convertis 10 km en miles', '180 livres en "
                "kg', '72 F en C'. value : le nombre ; from_unit et to_unit : les "
                "unites (km, mi, kg, lb, l, gal, C, F, K...). Pas de devises."
            ),
        )
        async def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
            """Convert a value between units locally."""
            debug_live("tool_call", tool="convert_units")
            result = await asyncio.to_thread(
                self.compute.convert_units, value, from_unit, to_unit,
            )
            self._debug_tool_result("convert_units", result)
            return result.to_livekit_dict()

        @function_tool(
            name="save_note",
            description=(
                "Enregistre une note dictee par l'utilisateur dans un fichier local "
                "('prends une note : ...', 'note que ...'). text : le contenu de la "
                "note ; title : un titre court optionnel. La note est sauvegardee "
                "dans le dossier Notes de Jarvis ; rien n'est envoye."
            ),
        )
        @self._journaled("save_note")
        async def save_note(text: str, title: str | None = None) -> dict:
            """Save a dictated note to a local Markdown file."""
            debug_live("tool_call", tool="save_note",
                       char_count=len(text) if isinstance(text, str) else None)
            result = await asyncio.to_thread(self.notes.save_note, text, title)
            self._debug_tool_result("save_note", result)
            return result.to_livekit_dict()

        @function_tool(
            name="list_notes",
            description=(
                "Liste les notes recemment enregistrees (nom, chemin). Pour 'mes "
                "notes', 'qu'est-ce que j'ai note'."
            ),
        )
        async def list_notes(limit: int = 10) -> dict:
            """List recent saved notes."""
            debug_live("tool_call", tool="list_notes")
            result = await asyncio.to_thread(self.notes.list_notes, limit)
            self._debug_tool_result("list_notes", result)
            return result.to_livekit_dict()

        @function_tool(
            name="list_calendar_events",
            description=(
                "Lit les evenements de l'agenda Apple pour un jour : "
                "'qu'est-ce que j'ai aujourd'hui', 'mon agenda de demain'. "
                "day_offset : 0 aujourd'hui, 1 demain, -1 hier."
            ),
        )
        async def list_calendar_events(day_offset: int = 0) -> dict:
            """Read Apple Calendar events for a day."""
            debug_live("tool_call", tool="list_calendar_events", day_offset=day_offset)
            result = await asyncio.to_thread(self.calendar.list_today, day_offset)
            self._debug_tool_result("list_calendar_events", result)
            return result.to_livekit_dict()

        @function_tool(
            name="create_calendar_event",
            description=(
                "PREPARE la creation d'un evenement dans l'agenda Apple, sans le "
                "creer tout de suite. Utilise ce tool pour 'ajoute un rendez-vous', "
                "'cree un evenement'. start et end sont des date/heure ISO 8601 "
                "absolues calculees depuis l'heure actuelle. Renvoie un token et "
                "requires_confirmation : annonce le titre, le jour et l'heure, puis "
                "confirm_action seulement sur un oui clair."
            ),
        )
        @self._journaled("create_calendar_event")
        async def create_calendar_event(title: str, start: str, end: str) -> dict:
            """Prepare an Apple Calendar event for confirmation."""
            debug_live("tool_call", tool="create_calendar_event")
            # Validate eagerly so the user is not asked to confirm a bad event.
            if not isinstance(title, str) or not title.strip():
                return ToolResult.failure(
                    action="create_calendar_event",
                    message="Le titre de l'evenement est obligatoire.",
                    error_code="invalid_title",
                ).to_livekit_dict()
            from jarvis.capabilities.calendar import _parse_iso
            try:
                start_dt = _parse_iso(start)
                end_dt = _parse_iso(end)
            except ValueError:
                return ToolResult.failure(
                    action="create_calendar_event",
                    message="Les dates doivent etre au format ISO 8601.",
                    error_code="invalid_datetime",
                ).to_livekit_dict()
            if end_dt <= start_dt:
                return ToolResult.failure(
                    action="create_calendar_event",
                    message="La fin doit etre apres le debut.",
                    error_code="invalid_range",
                ).to_livekit_dict()

            def _executor():
                return self.calendar.create_event(title, start, end)

            async with self.confirmation_lock:
                token = self.pending_actions.register("create_calendar_event", _executor)
            return ToolResult.success(
                action="create_calendar_event",
                message=(
                    "Evenement a confirmer. Annonce le titre, le jour et l'heure, "
                    "puis attends la confirmation avant confirm_action."
                ),
                requires_confirmation=True,
                token=token,
                title=title.strip(),
                start=start_dt.isoformat(timespec="minutes"),
                end=end_dt.isoformat(timespec="minutes"),
            ).to_livekit_dict()

        @function_tool(
            name="list_unread_emails",
            description=(
                "Lit les mails non lus de la boite de reception Apple Mail (sujet, "
                "expediteur, date) : 'mes mails non lus', 'qu'est-ce que j'ai recu'. "
                "limit : nombre maximum a remonter."
            ),
        )
        async def list_unread_emails(limit: int = 10) -> dict:
            """Read unread Apple Mail messages."""
            debug_live("tool_call", tool="list_unread_emails")
            result = await asyncio.to_thread(self.mail.list_unread, limit)
            self._debug_tool_result("list_unread_emails", result)
            return result.to_livekit_dict()

        @function_tool(
            name="summarize_unread_emails",
            description=(
                "Resume les mails NON LUS de la boite de reception en une phrase "
                "par mail, en local : 'resume mes mails', 'qu'est-ce que j'ai recu "
                "d'important'. Lit le corps des messages sans les marquer comme lus, "
                "et s'appuie uniquement sur leur contenu. Necessite IMAP configure. "
                "Le resume est genere et doit etre verifie ; aucun mail n'est envoye "
                "ni modifie. limit : nombre maximum de mails a resumer."
            ),
        )
        @self._journaled("summarize_unread_emails")
        async def summarize_unread_emails(limit: int = 5) -> dict:
            """Summarize unread Apple Mail messages with the local model."""
            debug_live("tool_call", tool="summarize_unread_emails", limit=limit)
            result = await asyncio.to_thread(self.mail.summarize_unread, limit)
            self._debug_tool_result("summarize_unread_emails", result)
            return result.to_livekit_dict()

        @function_tool(
            name="token_usage",
            description=(
                "Rapporte la consommation de tokens de Claude Code sur une periode, "
                "lue en local : 'combien de tokens j'ai consomme', 'ma conso cette "
                "semaine'. period : 'today', 'yesterday', '7d', '30d', '90d' ou 'all'. "
                "Donne les tokens generes, en entree et lus en cache. Aucune donnee "
                "ne quitte la machine."
            ),
        )
        async def token_usage(period: str = "7d") -> dict:
            """Report local Claude Code token consumption for a period."""
            debug_live("tool_call", tool="token_usage", period=period)
            result = await asyncio.to_thread(self.usage.overview, period)
            self._debug_tool_result("token_usage", result)
            return result.to_livekit_dict()

        @function_tool(
            name="token_usage_by_model",
            description=(
                "Repartit la consommation de tokens par modele (Opus, Sonnet...) sur "
                "une periode : 'ma conso par modele', 'quel modele consomme le plus'. "
                "period : 'today', '7d', '30d', '90d', 'all'. Inclut un cout estime "
                "equivalent API (indicatif ; l'abonnement n'est pas facture au token)."
            ),
        )
        async def token_usage_by_model(period: str = "30d") -> dict:
            """Break token usage down by model."""
            debug_live("tool_call", tool="token_usage_by_model", period=period)
            result = await asyncio.to_thread(self.usage.by_model, period)
            self._debug_tool_result("token_usage_by_model", result)
            return result.to_livekit_dict()

        @function_tool(
            name="token_usage_by_project",
            description=(
                "Repartit la consommation de tokens par projet (dossier de travail) "
                "sur une periode : 'ma conso par projet', 'sur quel projet je consomme "
                "le plus'. period : 'today', '7d', '30d', 'all' ; limit : nombre de "
                "projets a remonter."
            ),
        )
        async def token_usage_by_project(period: str = "30d", limit: int = 5) -> dict:
            """Break token usage down by project folder."""
            debug_live("tool_call", tool="token_usage_by_project", period=period, limit=limit)
            result = await asyncio.to_thread(self.usage.by_project, period, limit)
            self._debug_tool_result("token_usage_by_project", result)
            return result.to_livekit_dict()

        @function_tool(
            name="token_usage_trend",
            description=(
                "Donne la serie quotidienne de consommation de tokens pour tracer une "
                "courbe dans le temps : 'montre l'evolution de ma conso', 'un graphe "
                "sur deux semaines'. days : nombre de jours (2 a 120)."
            ),
        )
        async def token_usage_trend(days: int = 14) -> dict:
            """Daily token-usage series for charting."""
            debug_live("tool_call", tool="token_usage_trend", days=days)
            result = await asyncio.to_thread(self.usage.trend, days)
            self._debug_tool_result("token_usage_trend", result)
            return result.to_livekit_dict()

        @function_tool(
            name="compare_token_usage",
            description=(
                "Compare la consommation de tokens d'une periode avec la periode "
                "equivalente juste avant : 'est-ce que je consomme plus que la semaine "
                "derniere', 'compare ma conso'. period : '7d', '30d', '90d'."
            ),
        )
        async def compare_token_usage(period: str = "7d") -> dict:
            """Compare a period's token usage with the preceding equal window."""
            debug_live("tool_call", tool="compare_token_usage", period=period)
            result = await asyncio.to_thread(self.usage.compare, period)
            self._debug_tool_result("compare_token_usage", result)
            return result.to_livekit_dict()

        @function_tool(
            name="recent_claude_sessions",
            description=(
                "Liste tes dernieres sessions Claude Code avec, pour chacune, le "
                "projet, les tokens et un cout estime : 'mes dernieres sessions "
                "Claude', 'combien m'a coute ma derniere session'. Lecture locale. "
                "limit : nombre de sessions a remonter."
            ),
        )
        async def recent_claude_sessions(limit: int = 5) -> dict:
            """Recent Claude Code sessions with per-session tokens and cost."""
            debug_live("tool_call", tool="recent_claude_sessions", limit=limit)
            result = await asyncio.to_thread(self.usage.recent_sessions, limit)
            self._debug_tool_result("recent_claude_sessions", result)
            return result.to_livekit_dict()

        @function_tool(
            name="system_snapshot",
            description=(
                "Donne l'etat machine en direct : charge processeur, memoire, disque "
                "et batterie. 'comment va mon Mac', 'ma conso CPU la', 'il me reste "
                "combien de memoire'. Lecture locale instantanee."
            ),
        )
        async def system_snapshot() -> dict:
            """Live CPU/memory/disk/battery snapshot."""
            debug_live("tool_call", tool="system_snapshot")
            result = await asyncio.to_thread(self.system_metrics.snapshot)
            self._debug_tool_result("system_snapshot", result)
            return result.to_livekit_dict()

        @function_tool(
            name="top_processes",
            description=(
                "Liste les processus les plus gourmands du Mac : 'qu'est-ce qui "
                "bouffe mon CPU', 'quelle appli prend toute la memoire'. by : 'cpu' "
                "ou 'memory' ; limit : nombre de processus."
            ),
        )
        async def top_processes(by: str = "cpu", limit: int = 5) -> dict:
            """Heaviest processes by CPU or memory."""
            debug_live("tool_call", tool="top_processes", by=by, limit=limit)
            result = await asyncio.to_thread(self.system_metrics.top_processes, by, limit)
            self._debug_tool_result("top_processes", result)
            return result.to_livekit_dict()

        @function_tool(
            name="system_usage_history",
            description=(
                "Historique d'utilisation machine pour tracer une courbe dans le "
                "temps : 'l'evolution de mon CPU', 'un graphe de ma memoire sur la "
                "journee'. metric : 'cpu', 'memoire', 'disque', 'charge', 'batterie' ; "
                "period : '1h', '6h', '24h', '7d'. L'historique se remplit tant que "
                "Jarvis tourne."
            ),
        )
        async def system_usage_history(metric: str = "cpu", period: str = "24h") -> dict:
            """Bucketed machine-metric history for charting."""
            debug_live("tool_call", tool="system_usage_history", metric=metric, period=period)
            result = await asyncio.to_thread(self.system_metrics.history, metric, period)
            self._debug_tool_result("system_usage_history", result)
            return result.to_livekit_dict()

        @function_tool(
            name="check_anomalies",
            description=(
                "Verifie s'il se passe quelque chose d'anormal : processeur ou "
                "memoire satures depuis quelques minutes, disque presque plein, "
                "consommation de tokens Claude tres au-dessus de la normale du jour. "
                "'il y a un souci sur mon Mac', 'quelque chose d'anormal', 'pourquoi "
                "ca rame'. Lecture locale, rien ne quitte la machine."
            ),
        )
        async def check_anomalies() -> dict:
            """Explainable anomaly check over machine metrics and token usage."""
            debug_live("tool_call", tool="check_anomalies")
            result = await asyncio.to_thread(self.insights.check)
            self._debug_tool_result("check_anomalies", result)
            return result.to_livekit_dict()

        @function_tool(
            name="run_claude_task",
            description=(
                "Lance une session Claude Code EN TACHE DE FOND pour une consigne "
                "precise, recupere la reponse et la lit : 'demande a Claude de ...', "
                "'lance une session Claude pour ...'. prompt : la consigne ; "
                "directory : dossier de travail (optionnel, defaut : dossier "
                "personnel). Action consequente : renvoie un token et "
                "requires_confirmation. Annonce la consigne et le dossier, puis "
                "attends l'accord avant confirm_action. Rien n'est lance sans "
                "confirmation."
            ),
        )
        @self._journaled("run_claude_task")
        async def run_claude_task(prompt: str, directory: str = None) -> dict:
            """Prepare a one-shot Claude Code task (confirmation required)."""
            debug_live("tool_call", tool="run_claude_task",
                       prompt_length=len(prompt) if isinstance(prompt, str) else None)
            if not isinstance(prompt, str) or not prompt.strip():
                return ToolResult.failure("run_claude_task",
                                          "La consigne pour Claude est vide.",
                                          "invalid_prompt").to_livekit_dict()
            if not self.claude_sessions.available():
                return ToolResult.failure("run_claude_task",
                                          "Le CLI claude est introuvable.",
                                          "claude_missing").to_livekit_dict()

            def _executor():
                return self.claude_sessions.run_task(prompt, directory)

            async with self.confirmation_lock:
                token = self.pending_actions.register("run_claude_task", _executor)
            return ToolResult.success(
                "run_claude_task",
                "Tache Claude a confirmer. Annonce la consigne et le dossier, "
                "puis attends la confirmation avant confirm_action.",
                requires_confirmation=True, token=token,
                prompt=prompt.strip()[:160],
                directory=self.claude_sessions.resolve_directory(directory),
            ).to_livekit_dict()

        @function_tool(
            name="open_claude_session",
            description=(
                "Ouvre une session Claude Code INTERACTIVE dans une fenetre Terminal "
                "pour que l'utilisateur la pilote lui-meme : 'ouvre une session "
                "Claude', 'lance Claude dans le Terminal'. directory : dossier de "
                "travail (optionnel). Action consequente : renvoie un token et "
                "requires_confirmation. Annonce le dossier puis attends l'accord "
                "avant confirm_action."
            ),
        )
        @self._journaled("open_claude_session")
        async def open_claude_session(directory: str = None) -> dict:
            """Prepare opening an interactive Claude session (confirmation required)."""
            debug_live("tool_call", tool="open_claude_session")
            if not self.claude_sessions.available():
                return ToolResult.failure("open_claude_session",
                                          "Le CLI claude est introuvable.",
                                          "claude_missing").to_livekit_dict()

            def _executor():
                return self.claude_sessions.open_session(directory)

            async with self.confirmation_lock:
                token = self.pending_actions.register("open_claude_session", _executor)
            return ToolResult.success(
                "open_claude_session",
                "Ouverture de session Claude a confirmer. Annonce le dossier puis "
                "attends la confirmation avant confirm_action.",
                requires_confirmation=True, token=token,
                directory=self.claude_sessions.resolve_directory(directory),
            ).to_livekit_dict()

        @function_tool(
            name="draft_email",
            description=(
                "Cree un BROUILLON de mail dans Apple Mail (NON envoye) : "
                "'prepare un mail a ...', 'ecris un brouillon de reponse'. Le "
                "brouillon est enregistre dans Mail pour que l'utilisateur le relise "
                "et l'envoie lui-meme ; rien n'est envoye. recipient : adresse email ; "
                "subject : objet ; body : contenu."
            ),
        )
        @self._journaled("draft_email")
        @self._desktop_access
        async def draft_email(recipient: str, subject: str, body: str) -> dict:
            """Create an unsent Apple Mail draft."""
            debug_live("tool_call", tool="draft_email", body_length=len(body) if isinstance(body, str) else None)
            result = await asyncio.to_thread(self.mail.create_draft, recipient, subject, body)
            self._debug_tool_result("draft_email", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_brightness",
            description=(
                "Lit la luminosite actuelle de l'ecran principal du Mac. "
                "Utilise ce tool quand l'utilisateur demande la luminosite actuelle."
            ),
        )
        async def get_brightness() -> dict:
            """Read the current main display brightness."""
            debug_live("tool_call", tool="get_brightness")
            result = await asyncio.to_thread(self.system.get_brightness)
            self._debug_tool_result("get_brightness", result)
            return result.to_livekit_dict()

        @function_tool(
            name="set_brightness",
            description=(
                "Regle la luminosite de l'ecran principal du Mac a une valeur "
                "entiere entre 0 et 100, puis retourne la luminosite observee."
            ),
        )
        @self._journaled("set_brightness")
        async def set_brightness(level: int) -> dict:
            """Set the main display brightness to a value between 0 and 100."""
            debug_live("tool_call", tool="set_brightness", level=level)
            result = await asyncio.to_thread(self.system.set_brightness, level)
            self._debug_tool_result("set_brightness", result)
            return result.to_livekit_dict()

        @function_tool(
            name="lock_screen",
            description=(
                "Verrouille la session du Mac. Utilise ce tool uniquement "
                "quand l'utilisateur demande explicitement de verrouiller son Mac."
            ),
        )
        @self._journaled("lock_screen")
        @self._desktop_access
        async def lock_screen() -> dict:
            """Lock the current Mac session."""
            debug_live("tool_call", tool="lock_screen")
            result = await asyncio.to_thread(self.system.lock_screen)
            self._debug_tool_result("lock_screen", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_active_window",
            description=(
                "Lit la fenetre active reelle du Mac : application, titre, "
                "position, taille, et etats minimise ou plein ecran."
            ),
        )
        @self._desktop_access
        async def get_active_window() -> dict:
            """Read the currently active Mac window."""
            debug_live("tool_call", tool="get_active_window")
            result = await asyncio.to_thread(self.windows.get_active_window)
            self._debug_tool_result("get_active_window", result)
            return result.to_livekit_dict()

        @function_tool(
            name="focus_window",
            description=(
                "Met au premier plan une fenetre d'application macOS par nom "
                "d'application, puis verifie l'etat observe."
            ),
        )
        @self._journaled("focus_window", "app_name")
        @self._desktop_access
        async def focus_window(app_name: str) -> dict:
            """Focus a macOS application window."""
            debug_live("tool_call", tool="focus_window", app_name=app_name)
            result = await asyncio.to_thread(self.windows.focus_window, app_name)
            self._debug_tool_result("focus_window", result)
            return result.to_livekit_dict()

        @function_tool(
            name="minimize_window",
            description=(
                "Minimise la fenetre active, ou la fenetre d'une application "
                "si app_name est fourni, puis verifie l'etat observe."
            ),
        )
        @self._journaled("minimize_window", "app_name")
        @self._desktop_access
        async def minimize_window(app_name: str | None = None) -> dict:
            """Minimize the active window or an app window."""
            debug_live("tool_call", tool="minimize_window", app_name=app_name)
            result = await asyncio.to_thread(self.windows.minimize_window, app_name)
            self._debug_tool_result("minimize_window", result)
            return result.to_livekit_dict()

        @function_tool(
            name="maximize_window",
            description=(
                "Agrandit la fenetre active, ou la fenetre d'une application "
                "si app_name est fourni, dans le cadre utilisable sans activer "
                "le plein ecran macOS."
            ),
        )
        @self._journaled("maximize_window", "app_name")
        @self._desktop_access
        async def maximize_window(app_name: str | None = None) -> dict:
            """Maximize the active window or an app window without fullscreen."""
            debug_live("tool_call", tool="maximize_window", app_name=app_name)
            result = await asyncio.to_thread(self.windows.maximize_window, app_name)
            self._debug_tool_result("maximize_window", result)
            return result.to_livekit_dict()

        @function_tool(
            name="move_window",
            description=(
                "Deplace la fenetre active, ou la fenetre d'une application "
                "si app_name est fourni. position accepte uniquement left, "
                "right, center ou fullscreen."
            ),
        )
        @self._journaled("move_window", "app_name")
        @self._desktop_access
        async def move_window(position: str, app_name: str | None = None) -> dict:
            """Move the active window or an app window."""
            debug_live(
                "tool_call",
                tool="move_window",
                position=position,
                app_name=app_name,
            )
            result = await asyncio.to_thread(
                self.windows.move_window,
                position,
                app_name,
            )
            self._debug_tool_result("move_window", result)
            return result.to_livekit_dict()

        @function_tool(
            name="arrange_windows",
            description=(
                "Place deux applications cote a cote : la premiere sur la moitie "
                "gauche de l'ecran, la seconde sur la moitie droite ('mets Safari a "
                "gauche et Notes a droite', 'range ces deux fenetres'). left_app et "
                "right_app : les noms des applications."
            ),
        )
        @self._desktop_access
        async def arrange_windows(left_app: str, right_app: str) -> dict:
            """Tile two apps side by side."""
            debug_live("tool_call", tool="arrange_windows")
            result = await asyncio.to_thread(
                self.windows.arrange_side_by_side, left_app, right_app,
            )
            self._debug_tool_result("arrange_windows", result)
            return result.to_livekit_dict()

        @function_tool(
            name="list_files",
            description=(
                "Liste les fichiers et dossiers d'un chemin local macOS. "
                "Utilise ce tool pour connaitre le contenu actuel d'un dossier."
            ),
        )
        async def list_files(path: str | None = None) -> dict:
            """List files in a local folder."""
            debug_live("tool_call", tool="list_files", path=path)
            result = await asyncio.to_thread(self.files.list_files, path)
            self._debug_tool_result("list_files", result)
            return result.to_livekit_dict()

        @function_tool(
            name="find_files",
            description=(
                "Recherche de maniere bornee des fichiers ou dossiers locaux "
                "par nom, correspondance partielle ou extension."
            ),
        )
        async def find_files(query: str, path: str | None = None) -> dict:
            """Find files or folders by name in a local folder."""
            debug_live("tool_call", tool="find_files", query=query, path=path)
            result = await asyncio.to_thread(self.files.find_files, query, path)
            self._debug_tool_result("find_files", result)
            return result.to_livekit_dict()

        @function_tool(
            name="search_files_by_content",
            description=(
                "Recherche des fichiers locaux par CONTENU ou metadonnees via "
                "Spotlight (rapide, tout le dossier personnel) : 'retrouve mon CV', "
                "'le document qui parle du budget 2026', 'la facture EDF'. Pour une "
                "recherche par nom de fichier precis dans un dossier, prefere "
                "find_files."
            ),
        )
        async def search_files_by_content(query: str) -> dict:
            """Spotlight content/metadata search across the home folder."""
            debug_live("tool_call", tool="search_files_by_content", query_length=len(query) if isinstance(query, str) else None)
            result = await asyncio.to_thread(self.files.search_content, query)
            self._debug_tool_result("search_files_by_content", result)
            return result.to_livekit_dict()

        @function_tool(
            name="ask_about_document",
            description=(
                "Lit un document texte local et repond a une question a son sujet : "
                "'resume ce fichier', 'que dit ce document sur le budget', 'quelles "
                "sont les dates dans ce contrat'. path : le chemin du fichier (utilise "
                "find_files ou search_files_by_content pour le retrouver d'abord si "
                "besoin). Fonctionne sur du texte (txt, md, code, csv) et les PDF. "
                "La reponse se base uniquement sur le contenu du document."
            ),
        )
        @self._journaled("ask_about_document")
        async def ask_about_document(path: str, question: str) -> dict:
            """Answer a question about a local text document via the local model."""
            debug_live("tool_call", tool="ask_about_document")
            result = await asyncio.to_thread(self.document.ask, path, question)
            self._debug_tool_result("ask_about_document", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_file_info",
            description=(
                "Lit les informations actuelles d'un fichier ou dossier local : "
                "type, taille, date de modification et chemin absolu."
            ),
        )
        async def get_file_info(path: str) -> dict:
            """Read metadata for a local file or folder."""
            debug_live("tool_call", tool="get_file_info", path=path)
            result = await asyncio.to_thread(self.files.get_file_info, path)
            self._debug_tool_result("get_file_info", result)
            return result.to_livekit_dict()

        @function_tool(
            name="open_file",
            description=(
                "Ouvre un fichier local avec l'application macOS associee. "
                "Le chemin doit etre exact, idealement un chemin absolu retourne "
                "par un tool Files."
            ),
        )
        @self._journaled("open_file")
        @self._desktop_access
        async def open_file(path: str) -> dict:
            """Open a local file with macOS."""
            debug_live("tool_call", tool="open_file", path=path)
            result = await asyncio.to_thread(self.files.open_file, path)
            self._debug_tool_result("open_file", result)
            return result.to_livekit_dict()

        @function_tool(
            name="open_folder",
            description=(
                "Ouvre un dossier local dans Finder. Le chemin doit etre exact, "
                "idealement un chemin absolu retourne par un tool Files."
            ),
        )
        @self._journaled("open_folder")
        @self._desktop_access
        async def open_folder(path: str) -> dict:
            """Open a local folder in Finder."""
            debug_live("tool_call", tool="open_folder", path=path)
            result = await asyncio.to_thread(self.files.open_folder, path)
            self._debug_tool_result("open_folder", result)
            return result.to_livekit_dict()

        @function_tool(
            name="create_folder",
            description=(
                "Cree un dossier local sans ecraser de chemin existant, puis "
                "verifie son existence."
            ),
        )
        @self._journaled("create_folder")
        @self._desktop_access
        async def create_folder(path: str) -> dict:
            """Create a local folder without overwriting."""
            debug_live("tool_call", tool="create_folder", path=path)
            result = await asyncio.to_thread(self.files.create_folder, path)
            self._debug_tool_result("create_folder", result)
            return result.to_livekit_dict()

        @function_tool(
            name="rename_file",
            description=(
                "Renomme un fichier ou dossier local sans ecraser une destination "
                "existante, puis verifie le resultat."
            ),
        )
        @self._journaled("rename_file")
        @self._desktop_access
        async def rename_file(path: str, new_name: str) -> dict:
            """Rename a local file or folder without overwriting."""
            debug_live(
                "tool_call",
                tool="rename_file",
                path=path,
                new_name=new_name,
            )
            result = await asyncio.to_thread(
                self.files.rename_file,
                path,
                new_name,
            )
            self._debug_tool_result("rename_file", result)
            return result.to_livekit_dict()

        @function_tool(
            name="move_file",
            description=(
                "Deplace un fichier ou dossier local sans jamais ecraser de "
                "chemin existant. destination est soit le chemin final exact, "
                "soit un dossier existant (par exemple Documents ou Bureau) : "
                "l'element y est alors place en gardant son nom."
            ),
        )
        @self._journaled("move_file")
        @self._desktop_access
        async def move_file(source: str, destination: str) -> dict:
            """Move a local file or folder without overwriting."""
            debug_live(
                "tool_call",
                tool="move_file",
                source=source,
                destination=destination,
            )
            result = await asyncio.to_thread(
                self.files.move_file,
                source,
                destination,
            )
            self._debug_tool_result("move_file", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_clipboard_text",
            description=(
                "Lit le texte actuellement disponible dans le presse-papiers "
                "du Mac. Utilise ce tool pour savoir ce qui a ete copie ou "
                "si le presse-papiers contient du texte."
            ),
        )
        @self._desktop_access
        async def get_clipboard_text() -> dict:
            """Read current readable text from the Mac clipboard."""
            debug_live("tool_call", tool="get_clipboard_text")
            async with self.clipboard_lock:
                result = await asyncio.to_thread(
                    self.clipboard.get_clipboard_text,
                )
            self._debug_clipboard_result("get_clipboard_text", result)
            return result.to_livekit_dict()

        @function_tool(
            name="set_clipboard_text",
            description=(
                "Remplace le contenu texte du presse-papiers du Mac par le "
                "texte fourni, puis verifie que le texte relu est identique."
            ),
        )
        @self._desktop_access
        async def set_clipboard_text(text: str) -> dict:
            """Set Mac clipboard text and verify the result."""
            debug_live(
                "tool_call",
                tool="set_clipboard_text",
                length=len(text) if isinstance(text, str) else None,
            )
            async with self.clipboard_lock:
                result = await asyncio.to_thread(
                    self.clipboard.set_clipboard_text,
                    text,
                )
            self._debug_clipboard_result("set_clipboard_text", result)
            return result.to_livekit_dict()

        @function_tool(
            name="clear_clipboard",
            description=(
                "Efface le texte lisible du presse-papiers du Mac, puis "
                "verifie prudemment qu'aucun texte lisible n'est detecte."
            ),
        )
        @self._desktop_access
        async def clear_clipboard() -> dict:
            """Clear readable text from the Mac clipboard."""
            debug_live("tool_call", tool="clear_clipboard")
            async with self.clipboard_lock:
                result = await asyncio.to_thread(
                    self.clipboard.clear_clipboard,
                )
            self._debug_clipboard_result("clear_clipboard", result)
            return result.to_livekit_dict()

        @function_tool(
            name="rewrite_clipboard",
            description=(
                "Transforme le texte actuellement dans le presse-papiers selon une "
                "instruction (reformuler, corriger les fautes, traduire, resumer, "
                "changer le ton) et remet le resultat dans le presse-papiers pour "
                "que l'utilisateur le colle : 'corrige ce que j'ai copie', 'traduis "
                "ca en anglais', 'reformule plus poliment'. instruction : ce qu'il "
                "faut faire du texte."
            ),
        )
        @self._journaled("rewrite_clipboard")
        @self._desktop_access
        async def rewrite_clipboard(instruction: str) -> dict:
            """Transform the clipboard text with the local model."""
            debug_live("tool_call", tool="rewrite_clipboard")
            async with self.clipboard_lock:
                result = await asyncio.to_thread(
                    self.text_workshop.rewrite_clipboard, instruction,
                )
            self._debug_tool_result("rewrite_clipboard", result)
            return result.to_livekit_dict()

        @function_tool(
            name="type_text",
            description=(
                "Saisit le texte fourni dans la fenetre macOS actuellement "
                "active. N'appuie jamais automatiquement sur Entree."
            ),
        )
        @self._desktop_access
        async def type_text(text: str) -> dict:
            """Type text into the currently active macOS window."""
            debug_live(
                "tool_call",
                tool="type_text",
                length=len(text) if isinstance(text, str) else None,
            )
            async with self.keyboard_lock:
                result = await asyncio.to_thread(self.keyboard.type_text, text)
            self._debug_keyboard_result("type_text", result)
            return result.to_livekit_dict()

        @function_tool(
            name="press_key",
            description=(
                "Appuie sur une touche clavier autorisee dans la fenetre "
                "macOS actuellement active : enter, escape, tab, space, "
                "arrow_up, arrow_down, arrow_left ou arrow_right."
            ),
        )
        @self._desktop_access
        async def press_key(key: str) -> dict:
            """Press one allowed key in the currently active macOS window."""
            debug_live("tool_call", tool="press_key", key=key)
            async with self.keyboard_lock:
                result = await asyncio.to_thread(self.keyboard.press_key, key)
            self._debug_keyboard_result("press_key", result)
            return result.to_livekit_dict()

        @function_tool(
            name="hotkey",
            description=(
                "Envoie un raccourci clavier explicitement autorise dans la "
                "fenetre macOS actuellement active. Passe keys comme une "
                'liste separee, par exemple ["command", "a"] ou '
                '["command", "shift", "z"]. Raccourcis V1 : command+a, '
                "command+c, command+v, command+z, command+shift+z, "
                "command+f, command+s."
            ),
        )
        @self._desktop_access
        async def hotkey(keys: list[str]) -> dict:
            """Send one allowed hotkey in the active macOS window."""
            debug_live("tool_call", tool="hotkey", keys=keys)
            async with self.keyboard_lock:
                result = await asyncio.to_thread(self.keyboard.hotkey, keys)
            self._debug_keyboard_result("hotkey", result)
            return result.to_livekit_dict()

        @function_tool(
            name="get_mouse_position",
            description=(
                "Lit la position actuelle reelle du pointeur de souris dans "
                "les coordonnees globales macOS."
            ),
        )
        @self._desktop_access
        async def get_mouse_position() -> dict:
            """Read the current mouse pointer position."""
            debug_live("tool_call", tool="get_mouse_position")
            async with self.mouse_lock:
                result = await asyncio.to_thread(self.mouse.get_mouse_position)
            self._debug_mouse_result("get_mouse_position", result)
            return result.to_livekit_dict()

        @function_tool(
            name="move_mouse",
            description=(
                "Deplace le pointeur de souris vers des coordonnees macOS "
                "explicites x/y. Ne devine jamais ces coordonnees."
            ),
        )
        @self._desktop_access
        async def move_mouse(x: int, y: int) -> dict:
            """Move the mouse pointer to explicit macOS coordinates."""
            debug_live("tool_call", tool="move_mouse", x=x, y=y)
            async with self.mouse_lock:
                result = await asyncio.to_thread(self.mouse.move_mouse, x, y)
            self._debug_mouse_result("move_mouse", result)
            return result.to_livekit_dict()

        @function_tool(
            name="click",
            description=(
                "Envoie un clic gauche a la position actuelle du pointeur. "
                "Ce tool ne confirme pas l'effet applicatif du clic."
            ),
        )
        @self._desktop_access
        async def click() -> dict:
            """Send one left click at the current mouse position."""
            debug_live("tool_call", tool="click")
            async with self.mouse_lock:
                result = await asyncio.to_thread(self.mouse.click)
            self._debug_mouse_result("click", result)
            return result.to_livekit_dict()

        @function_tool(
            name="double_click",
            description=(
                "Envoie un double clic gauche a la position actuelle du "
                "pointeur. Ce tool ne confirme pas l'effet applicatif."
            ),
        )
        @self._desktop_access
        async def double_click() -> dict:
            """Send one double left click at the current mouse position."""
            debug_live("tool_call", tool="double_click")
            async with self.mouse_lock:
                result = await asyncio.to_thread(self.mouse.double_click)
            self._debug_mouse_result("double_click", result)
            return result.to_livekit_dict()

        @function_tool(
            name="right_click",
            description=(
                "Envoie un clic droit a la position actuelle du pointeur. "
                "Ce tool ne confirme pas l'effet applicatif du clic."
            ),
        )
        @self._desktop_access
        async def right_click() -> dict:
            """Send one right click at the current mouse position."""
            debug_live("tool_call", tool="right_click")
            async with self.mouse_lock:
                result = await asyncio.to_thread(self.mouse.right_click)
            self._debug_mouse_result("right_click", result)
            return result.to_livekit_dict()

        @function_tool(
            name="scroll",
            description=(
                "Envoie un scroll souris dans une direction explicite : up, "
                "down, left ou right, avec amount entre 1 et 10."
            ),
        )
        @self._desktop_access
        async def scroll(direction: str, amount: int = 3) -> dict:
            """Send a bounded mouse scroll command."""
            debug_live(
                "tool_call",
                tool="scroll",
                direction=direction,
                amount=amount,
            )
            async with self.mouse_lock:
                result = await asyncio.to_thread(
                    self.mouse.scroll,
                    direction,
                    amount,
                )
            self._debug_mouse_result("scroll", result)
            return result.to_livekit_dict()

        @function_tool(
            name="inspect_ui",
            description=(
                "Inspecte les elements Accessibility utiles dans la fenetre "
                "macOS actuelle, avec une profondeur et un nombre d'elements bornes."
            ),
        )
        @self._desktop_access
        async def inspect_ui(max_depth: int = 4, max_elements: int = 80) -> dict:
            """Inspect the current macOS Accessibility UI tree."""
            debug_live(
                "tool_call",
                tool="inspect_ui",
                max_depth=max_depth,
                max_elements=max_elements,
            )
            async with self.ui_lock:
                result = await asyncio.to_thread(
                    self.ui_accessibility.inspect_ui,
                    max_depth,
                    max_elements,
                )
            self._debug_ui_result("inspect_ui", result)
            return result.to_livekit_dict()

        @function_tool(
            name="find_ui_elements",
            description=(
                "Recherche des elements Accessibility par nom ou label humain. "
                "role est optionnel et ne doit etre fourni que s'il est utile."
            ),
        )
        @self._desktop_access
        async def find_ui_elements(query: str, role: str | None = None) -> dict:
            """Find current macOS Accessibility UI elements by human label."""
            debug_live(
                "tool_call",
                tool="find_ui_elements",
                query_length=len(query) if isinstance(query, str) else None,
                role=role,
            )
            async with self.ui_lock:
                result = await asyncio.to_thread(
                    self.ui_accessibility.find_ui_elements,
                    query,
                    role,
                )
            self._debug_ui_result("find_ui_elements", result)
            return result.to_livekit_dict()

        @function_tool(
            name="focus_ui_element",
            description=(
                "Met le focus Accessibility sur un element nomme de "
                "l'interface actuelle. L'element est re-resolu juste avant l'action."
            ),
        )
        @self._desktop_access
        async def focus_ui_element(query: str, role: str | None = None) -> dict:
            """Focus one current macOS Accessibility UI element."""
            debug_live(
                "tool_call",
                tool="focus_ui_element",
                query_length=len(query) if isinstance(query, str) else None,
                role=role,
            )
            async with self.ui_lock:
                result = await asyncio.to_thread(
                    self.ui_accessibility.focus_ui_element,
                    query,
                    role,
                )
            self._debug_ui_result("focus_ui_element", result)
            return result.to_livekit_dict()

        @function_tool(
            name="activate_ui_element",
            description=(
                "Active un element Accessibility nomme avec AXPress lorsque "
                "l'element expose cette action. Aucun fallback souris automatique."
            ),
        )
        @self._desktop_access
        async def activate_ui_element(query: str, role: str | None = None) -> dict:
            """Activate one current macOS Accessibility UI element with AXPress."""
            debug_live(
                "tool_call",
                tool="activate_ui_element",
                query_length=len(query) if isinstance(query, str) else None,
                role=role,
            )
            async with self.ui_lock:
                result = await asyncio.to_thread(
                    self.ui_accessibility.activate_ui_element,
                    query,
                    role,
                )
            self._debug_ui_result("activate_ui_element", result)
            return result.to_livekit_dict()

        @function_tool(
            name="click_element",
            description=(
                "Clique sur un element de l'ecran decrit par l'utilisateur ('clique "
                "sur Valider', 'clique sur le bouton bleu Envoyer'), en combinant ce "
                "qui est affiche et l'Accessibility. Les coordonnees viennent "
                "TOUJOURS de l'Accessibility, jamais devinees depuis l'image : si "
                "l'element n'est pas expose par Accessibility, Jarvis refuse plutot "
                "que de cliquer a l'aveugle. Il utilise AXPress quand c'est possible, "
                "sinon un clic au centre de la position Accessibility de l'element. "
                "Pour voir ce qui est affiche/cliquable, describe_screen ou "
                "inspect_ui. query : description de l'element."
            ),
        )
        @self._journaled("click_element")
        @self._desktop_access
        async def click_element(query: str, role: str | None = None) -> dict:
            """Click an element by its Accessibility-grounded position (never blind)."""
            debug_live("tool_call", tool="click_element",
                       query_length=len(query) if isinstance(query, str) else None)
            located = await asyncio.to_thread(self.ui_accessibility.locate, query, role)
            if not located.ok:
                return located.to_livekit_dict()
            candidate = located.data.get("candidate") or {}
            actions = candidate.get("actions") or []

            if "AXPress" in actions:
                async with self.ui_lock:
                    result = await asyncio.to_thread(
                        self.ui_accessibility.activate_ui_element, query, role,
                    )
                self._debug_ui_result("click_element", result)
                return result.to_livekit_dict()

            position = candidate.get("position")
            size = candidate.get("size")
            if not (isinstance(position, dict) and isinstance(size, dict)):
                return ToolResult.failure(
                    action="click_element",
                    message=(
                        "Cet element n'expose ni action ni position via Accessibility ; "
                        "je ne clique pas a l'aveugle."
                    ),
                    error_code="no_grounded_target",
                ).to_livekit_dict()

            center_x = int(position["x"] + size["width"] / 2)
            center_y = int(position["y"] + size["height"] / 2)
            async with self.mouse_lock:
                move = await asyncio.to_thread(self.mouse.move_mouse, center_x, center_y)
                if not move.ok or move.data.get("state_confirmed") is not True:
                    return ToolResult.failure(
                        action="click_element",
                        message="Impossible de positionner le pointeur sur l'element.",
                        error_code="move_failed",
                    ).to_livekit_dict()
                await asyncio.to_thread(self.mouse.click)
            return ToolResult.success(
                action="click_element",
                message=(
                    "Clic envoye au centre de l'element (coordonnees Accessibility). "
                    "L'effet applicatif n'est pas confirme."
                ),
                command_executed=True,
                state_confirmed=False,
                x=center_x,
                y=center_y,
                grounded="accessibility",
            ).to_livekit_dict()

        @function_tool(
            name="select_all_and_copy",
            description=(
                "Selectionne tout puis copie dans la fenetre active avec une "
                "sequence mecanique command+a puis command+c. Utilise ce tool "
                "pour les demandes naturelles comme selectionne tout et copie."
            ),
        )
        @self._desktop_access
        async def select_all_and_copy() -> dict:
            """Run command+a then command+c as one ordered interaction."""
            debug_live("tool_call", tool="select_all_and_copy")
            async with self.interaction_lock:
                result = await asyncio.to_thread(
                    self.interaction.select_all_and_copy,
                )
            self._debug_interaction_result("select_all_and_copy", result)
            return result.to_livekit_dict()

        @function_tool(
            name="focus_app_ui_and_type",
            description=(
                "Ouvre ou focalise une application, focalise "
                "une cible Accessibility nommee, puis saisit du texte seulement "
                "si la cible est verifiee. Utilise ce tool pour ouvrir une app "
                "et ecrire dans une cible naturelle comme une barre de recherche. "
                "Fournis obligatoirement query pour toute cible semantique nommee ou "
                "impliquee, meme si l'application est connue : recherche/navigation "
                "=> query='recherche', champ Nom => query='Nom'. query=None accepte "
                "uniquement un champ editable actuellement focalise et verifie via "
                "Accessibility ; sinon editable_target_not_verified, aucune saisie ni Enter. "
                "press_enter suit uniquement une saisie executee apres validation. "
                "command_executed ne prouve pas le succes de la recherche/navigation."
            ),
        )
        @self._journaled("focus_app_ui_and_type", "app_name")
        @self._desktop_access
        async def focus_app_ui_and_type(
            app_name: str,
            text: str,
            query: str | None = None,
            role: str | None = None,
            press_enter: bool = False,
        ) -> dict:
            """Focus an app/UI target, then type text in a verified sequence."""
            debug_live(
                "tool_call",
                tool="focus_app_ui_and_type",
                app_name=app_name,
                text_length=len(text) if isinstance(text, str) else None,
                query_length=len(query) if isinstance(query, str) else None,
                role=role,
                press_enter=press_enter,
            )
            async with self.interaction_lock:
                result = await asyncio.to_thread(
                    self.interaction.focus_app_ui_and_type,
                    app_name,
                    text,
                    query,
                    role,
                    press_enter,
                )
            self._debug_interaction_result("focus_app_ui_and_type", result)
            return result.to_livekit_dict()

        @function_tool(
            name="open_app_and_focus_ui",
            description=(
                "Ouvre ou focalise une application puis focalise une cible "
                "Accessibility nommee, sans taper de texte. Utilise ce tool "
                "pour ouvrir une app et mettre le curseur dans un champ nomme."
            ),
        )
        @self._journaled("open_app_and_focus_ui", "app_name")
        @self._desktop_access
        async def open_app_and_focus_ui(
            app_name: str,
            query: str,
            role: str | None = None,
        ) -> dict:
            """Open/focus an app and focus one named UI element."""
            debug_live(
                "tool_call",
                tool="open_app_and_focus_ui",
                app_name=app_name,
                query_length=len(query) if isinstance(query, str) else None,
                role=role,
            )
            async with self.interaction_lock:
                result = await asyncio.to_thread(
                    self.interaction.open_app_and_focus_ui,
                    app_name,
                    query,
                    role,
                )
            self._debug_interaction_result("open_app_and_focus_ui", result)
            return result.to_livekit_dict()

        @function_tool(
            name="select_all_and_delete",
            description=(
                "Selectionne tout puis supprime le texte dans le champ editable "
                "actuellement focalise : verifie d'abord une cible editable sure, "
                "puis command+a, puis une suppression unique (Backspace). Utilise "
                "ce tool pour les demandes comme selectionne tout et supprime ou "
                "efface tout le texte. N'utilise jamais select_all_and_copy pour "
                "supprimer, et ne simule jamais la suppression avec Escape ou "
                "Entree. N'efface aucun fichier et ne copie rien. state_confirmed "
                "reste false : l'effacement du champ ne peut pas etre confirme."
            ),
        )
        @self._desktop_access
        async def select_all_and_delete() -> dict:
            """Verify an editable target, then Command+A and one Backspace."""
            debug_live("tool_call", tool="select_all_and_delete")
            async with self.interaction_lock:
                result = await asyncio.to_thread(
                    self.interaction.select_all_and_delete,
                )
            self._debug_interaction_result("select_all_and_delete", result)
            return result.to_livekit_dict()

        @function_tool(
            name="send_prompt_to_app",
            description=(
                "Ouvre ou focalise une application de chat (par exemple Claude), "
                "verifie le champ de saisie editable focalise, y saisit le texte "
                "puis valide avec Entree pour l'envoyer. Utilise ce tool pour une "
                "demande comme demande a Claude de ..., ouvre Claude et ecris ... "
                "ou lance une discussion avec Claude sur ... Fournis query "
                "seulement si un champ precis est nomme ; sinon la saisie va dans "
                "le champ editable actuellement focalise, qui doit etre verifie "
                "via Accessibility. Si editable_target_not_verified est retourne, "
                "rien n'a ete saisi ni envoye : demande une clarification. "
                "command_executed signifie que la saisie et la validation ont ete "
                "envoyees, pas que l'application a traite la demande."
            ),
        )
        @self._journaled("send_prompt_to_app", "app_name")
        @self._desktop_access
        async def send_prompt_to_app(
            app_name: str,
            text: str,
            query: str | None = None,
        ) -> dict:
            """Open/focus an app, type a prompt into it, and submit with Enter."""
            debug_live(
                "tool_call",
                tool="send_prompt_to_app",
                app_name=app_name,
                text_length=len(text) if isinstance(text, str) else None,
                query_length=len(query) if isinstance(query, str) else None,
            )
            direct = (
                not (isinstance(query, str) and query.strip())
                and isinstance(app_name, str)
                and app_name.strip().casefold() in DIRECT_PROMPT_APPS
            )
            async with self.interaction_lock:
                if direct:
                    # Electron/web apps (e.g. Claude) expose no targetable AX
                    # field: confirm the app is frontmost, then type directly.
                    result = await asyncio.to_thread(
                        self.interaction.open_app_and_type,
                        app_name,
                        text,
                        True,
                    )
                else:
                    result = await asyncio.to_thread(
                        self.interaction.focus_app_ui_and_type,
                        app_name,
                        text,
                        query,
                        None,
                        True,
                    )
            self._debug_interaction_result("send_prompt_to_app", result)
            return result.to_livekit_dict()

        @function_tool(
            name="prepare_send_message",
            description=(
                "PREPARE l'envoi d'un message a un destinataire dans une "
                "application de messagerie (par exemple WhatsApp), SANS l'envoyer. "
                "Enregistre l'envoi et renvoie un token et requires_confirmation. "
                "Utilise ce tool des que l'utilisateur veut envoyer un message a "
                "une personne, un contact ou un groupe. Apres l'avoir appele, "
                "annonce clairement a l'utilisateur l'application, le destinataire "
                "et le contenu exact, puis attends une confirmation orale "
                "explicite. N'envoie rien ici ; l'envoi reel se fait uniquement "
                "ensuite via confirm_action(token). query cible un champ de saisie "
                "nomme si besoin. Fournis recipient (le nom du destinataire) pour "
                "que Jarvis verifie d'abord que la conversation ouverte correspond "
                "bien ; si recipient_not_verified est retourne, rien n'est prepare "
                "et il faut ouvrir la bonne conversation. N'utilise pas ce tool "
                "pour un simple prompt a un assistant comme Claude : utilise "
                "send_prompt_to_app pour cela."
            ),
        )
        @self._journaled("prepare_send_message", "app_name")
        @self._desktop_access
        async def prepare_send_message(
            app_name: str,
            text: str,
            recipient: str | None = None,
            query: str | None = None,
        ) -> dict:
            """Register a message send for confirmation; no side effect here."""
            if not isinstance(app_name, str) or not app_name.strip():
                return ToolResult.failure(
                    action="prepare_send_message",
                    message="Le nom de l'application de messagerie est obligatoire.",
                    error_code="invalid_app_name",
                ).to_livekit_dict()

            if not isinstance(text, str) or not text.strip():
                return ToolResult.failure(
                    action="prepare_send_message",
                    message="Le message a envoyer est obligatoire.",
                    error_code="invalid_text",
                ).to_livekit_dict()

            recipient_from_memory = False
            if isinstance(recipient, str) and recipient.strip():
                # Apply memory locally: "ma mere" -> stored contact name. The
                # model never needs (nor receives) the stored name.
                async with self.memory_lock:
                    resolved = await asyncio.to_thread(
                        self.memory.resolve_person, recipient,
                    )
                if resolved:
                    recipient = resolved
                    recipient_from_memory = True

                verification = await asyncio.to_thread(
                    self.messaging.ensure_recipient,
                    app_name,
                    recipient,
                )
                self._debug_interaction_result("ensure_recipient", verification)
                if not verification.ok:
                    # Fail safe: never prepare a send against an unverified chat.
                    return verification.to_livekit_dict()

            # Target the app's composer by default (e.g. WhatsApp's is not
            # focused on its own); an explicit query still wins.
            effective_query = (
                query
                if isinstance(query, str) and query.strip()
                else self.messaging.composer_query(app_name)
            )

            def _executor():
                # Verified composer send for messaging apps that support it
                # (writes + reads back the composer, then presses send) -- the
                # WhatsApp composer never confirms programmatic focus, so the
                # focus + type path cannot reach it. Unknown apps keep the old
                # focus + type path unchanged.
                if (
                    not (isinstance(query, str) and query.strip())
                    and self.messaging.supports_composer_send(app_name)
                ):
                    return self.messaging.send_text(app_name, text)
                return self.interaction.focus_app_ui_and_type(
                    app_name, text, effective_query, None, True,
                )

            async with self.confirmation_lock:
                token = self.pending_actions.register("send_message", _executor)

            debug_live(
                "tool_call",
                tool="prepare_send_message",
                app_name=app_name,
                text_length=len(text),
                query_length=len(query) if isinstance(query, str) else None,
                token=token,
            )
            return ToolResult.success(
                action="prepare_send_message",
                message=(
                    "Envoi prepare. Annonce le destinataire et le contenu a "
                    "l'utilisateur et attends sa confirmation avant confirm_action."
                ),
                requires_confirmation=True,
                token=token,
                target_app=app_name,
                text_length=len(text),
                query_length=len(query) if isinstance(query, str) else None,
                recipient_verified=bool(isinstance(recipient, str) and recipient.strip()),
                recipient_from_memory=recipient_from_memory,
            ).to_livekit_dict()

        @function_tool(
            name="send_last_web_result",
            description=(
                "PREPARE l'envoi du resultat de la DERNIERE recherche web (celle "
                "annoncee juste avant) a un destinataire, sans l'envoyer. Utilise ce "
                "tool quand l'utilisateur dit 'envoie ca', 'partage ces nouvelles a "
                "...', 'envoie-moi ce recap' apres une recherche. Le contenu exact "
                "trouve est repris tel quel (tu n'as pas a le reecrire). Comme pour "
                "tout envoi, annonce ensuite l'application, le destinataire et le "
                "contenu, puis attends un oui clair avant confirm_action(token). "
                "app_name : l'application (par exemple WhatsApp) ; recipient : le nom "
                "du destinataire."
            ),
        )
        @self._journaled("send_last_web_result", "app_name")
        @self._desktop_access
        async def send_last_web_result(
            app_name: str,
            recipient: str | None = None,
        ) -> dict:
            """Prepare sending the last web answer, verbatim, via prepare_send_message."""
            debug_live("tool_call", tool="send_last_web_result", app_name=app_name)
            if not self._last_web_result_text:
                return ToolResult.failure(
                    action="send_last_web_result",
                    message=(
                        "Aucun resultat de recherche recent a envoyer. Fais d'abord "
                        "une recherche avec search_the_web."
                    ),
                    error_code="no_recent_web_result",
                ).to_livekit_dict()
            # Reuse the verified two-step send flow unchanged.
            return await prepare_send_message(
                app_name=app_name,
                text=self._last_web_result_text,
                recipient=recipient,
            )

        @function_tool(
            name="remember",
            description=(
                "Enregistre un souvenir durable UNIQUEMENT quand l'utilisateur "
                "demande explicitement de retenir quelque chose (souviens-toi, "
                "retiens, note que...). kind : profile (infos sur l'utilisateur), "
                "person (subject = surnom ou relation comme 'ma mere', content = "
                "nom exact du contact dans les apps), preference (subject = "
                "domaine comme 'musique', content = la preference, par exemple "
                "'Spotify' ou 'Apple Music'), fact (autre "
                "information utile). Un souvenir de meme kind et subject est mis "
                "a jour. Pour une information que tu as seulement deduite, "
                "utilise propose_memory. Les secrets sont toujours refuses."
            ),
        )
        @self._journaled("remember")
        async def remember(kind: str, subject: str, content: str) -> dict:
            """Store an explicitly requested long-term memory."""
            debug_live("tool_call", tool="remember", kind=kind)
            async with self.memory_lock:
                result = await asyncio.to_thread(
                    self.memory.remember, kind, subject, content, "user",
                )
            self._debug_tool_result("remember", result)
            return result.to_livekit_dict()

        @function_tool(
            name="propose_memory",
            description=(
                "Propose de retenir une information que tu as DEDUITE sans que "
                "l'utilisateur demande de la retenir (par exemple il corrige deux "
                "fois le meme nom de contact). N'enregistre rien : renvoie un "
                "token et requires_confirmation. Demande alors a l'utilisateur, "
                "en une phrase, s'il veut que tu retiennes cette information ; "
                "seulement apres un oui clair, appelle confirm_action(token). "
                "Sinon cancel_action(token). Memes kind que remember."
            ),
        )
        async def propose_memory(kind: str, subject: str, content: str) -> dict:
            """Register an inferred memory that is stored only on confirmation."""
            debug_live("tool_call", tool="propose_memory", kind=kind)
            refusal = self.memory.check_proposal(kind, subject, content)
            if refusal is not None:
                return refusal.to_livekit_dict()

            def _executor():
                return self.memory.remember(kind, subject, content, "inferred")

            async with self.confirmation_lock:
                token = self.pending_actions.register("remember_inferred", _executor)

            return ToolResult.success(
                action="propose_memory",
                message=(
                    "Rien n'est enregistre. Demande a l'utilisateur s'il veut que "
                    "tu retiennes cette information, puis confirm_action ou "
                    "cancel_action."
                ),
                requires_confirmation=True,
                token=token,
            ).to_livekit_dict()

        @function_tool(
            name="recall",
            description=(
                "Cherche dans la memoire durable de l'utilisateur (profil, "
                "personnes, preferences, faits). Utilise ce tool quand "
                "l'utilisateur pose une question sur ce qu'il t'a demande de "
                "retenir, ou quand une information personnelle manque pour "
                "repondre (par exemple le nom de son dentiste). kind optionnel "
                "pour filtrer. Ne reponds jamais 'je ne sais pas' sur un sujet "
                "personnel sans avoir appele recall."
            ),
        )
        async def recall(query: str, kind: str | None = None) -> dict:
            """Search long-term memory."""
            debug_live("tool_call", tool="recall", kind=kind)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.recall, query, kind)
            self._debug_tool_result("recall", result)
            return result.to_livekit_dict()

        @function_tool(
            name="list_memories",
            description=(
                "Liste les souvenirs enregistres, eventuellement filtres par kind. "
                "Utilise ce tool pour 'qu'est-ce que tu sais sur moi' ou 'quels "
                "contacts tu connais'."
            ),
        )
        async def list_memories(kind: str | None = None) -> dict:
            """List stored memories."""
            debug_live("tool_call", tool="list_memories", kind=kind)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.list_memories, kind)
            self._debug_tool_result("list_memories", result)
            return result.to_livekit_dict()

        @function_tool(
            name="forget",
            description=(
                "Oublie definitivement un souvenir quand l'utilisateur le demande "
                "(oublie que..., efface ce que tu sais sur...). Fournis memory_id "
                "si tu le connais, sinon query. Si ambiguous_memory est retourne, "
                "rien n'est efface : presente les candidats et demande lequel."
            ),
        )
        @self._journaled("forget")
        async def forget(memory_id: int | None = None, query: str | None = None) -> dict:
            """Delete one memory by id or unambiguous query."""
            debug_live("tool_call", tool="forget", memory_id=memory_id)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.forget, memory_id, query)
            self._debug_tool_result("forget", result)
            return result.to_livekit_dict()

        @function_tool(
            name="recent_activity",
            description=(
                "Relit le journal des dernieres actions realisees par Jarvis "
                "(ouvrir une app, changer le volume, preparer ou envoyer un "
                "message, ouvrir un site...), avec l'heure et le resultat. Le "
                "journal ne contient jamais le texte des messages ni le contenu "
                "manipule. Utilise ce tool pour 'qu'est-ce que tu as fait', "
                "'tu as bien envoye le message ?' ou 'refais comme tout a l'heure'."
            ),
        )
        async def recent_activity(limit: int = 10) -> dict:
            """Read the most recent journaled actions."""
            debug_live("tool_call", tool="recent_activity", limit=limit)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.recent_activity, limit)
            self._debug_tool_result("recent_activity", result)
            return result.to_livekit_dict()

        @function_tool(
            name="recent_missions",
            description=(
                "Liste les dernieres missions en arriere-plan (run_task) avec leur "
                "objectif, leur statut final (terminee, echec, annulee...) et "
                "l'heure. Contrairement a task_status qui ne voit que la session "
                "en cours, cet historique est conserve localement et SURVIT a un "
                "redemarrage de Jarvis. Utilise ce tool pour 'quelles etaient mes "
                "dernieres missions', 'qu'est-ce que tu as lance tout a l'heure', "
                "'la mission d'hier a-t-elle abouti'."
            ),
        )
        async def recent_missions(limit: int = 10) -> dict:
            """Read the most recent persisted missions (survives restarts)."""
            debug_live("tool_call", tool="recent_missions", limit=limit)
            async with self.memory_lock:
                result = await asyncio.to_thread(self.memory.recent_missions, limit)
            self._debug_tool_result("recent_missions", result)
            return result.to_livekit_dict()

        @function_tool(
            name="confirm_action",
            description=(
                "Execute reellement une action preparee (envoi de message ou "
                "souvenir deduit a enregistrer) en utilisant le token renvoye par "
                "prepare_send_message ou propose_memory. N'appelle ce tool "
                "qu'APRES une confirmation orale explicite de l'utilisateur. "
                "N'invente jamais de token et ne l'appelle jamais sans preparation "
                "prealable. Si aucune action n'est en attente, il retourne "
                "no_pending_action."
            ),
        )
        @self._desktop_access
        async def confirm_action(token: str) -> dict:
            """Execute a previously prepared outward action after confirmation."""
            debug_live("tool_call", tool="confirm_action", token=token)
            async with self.confirmation_lock:
                pending = self.pending_actions.confirm(token)

            if pending is None:
                debug_live("tool_failed", tool="confirm_action", error="no_pending_action")
                return ToolResult.failure(
                    action="confirm_action",
                    message=(
                        "Aucune action en attente de confirmation (ou expiree). "
                        "Rien n'a ete envoye."
                    ),
                    error_code="no_pending_action",
                ).to_livekit_dict()

            result = await asyncio.to_thread(pending.executor)
            self._debug_interaction_result(f"confirm_action:{pending.action}", result)
            payload = result.to_livekit_dict()
            await self._log_action(f"confirm_{pending.action}", None, payload)
            return payload

        @function_tool(
            name="cancel_action",
            description=(
                "Annule une action sortante preparee (par exemple un envoi de "
                "message) sans l'executer, en utilisant son token. Utilise ce tool "
                "si l'utilisateur refuse, hesite ou se retracte apres une "
                "preparation. Rien n'est envoye."
            ),
        )
        async def cancel_action(token: str) -> dict:
            """Discard a prepared outward action without executing it."""
            debug_live("tool_call", tool="cancel_action", token=token)
            async with self.confirmation_lock:
                pending = self.pending_actions.cancel(token)

            cancelled = pending is not None
            debug_live(
                "tool_succeeded" if cancelled else "tool_failed",
                tool="cancel_action",
                cancelled=cancelled,
            )
            return ToolResult.success(
                action="cancel_action",
                message=(
                    "Action annulee, rien n'a ete envoye."
                    if cancelled
                    else "Aucune action en attente a annuler."
                ),
                cancelled=cancelled,
            ).to_livekit_dict()

        @function_tool(
            name="browse_open_url",
            description=(
                "Ouvre une URL dans Safari ou Google Chrome, active la fenetre "
                "puis relit l'onglet actif pour verifier le chargement. Utilise "
                "ce tool pour aller sur un site. browser=None choisit "
                "automatiquement le navigateur ouvert (Safari par defaut). "
                "new_tab=true ouvre un nouvel onglet, false reutilise l'onglet "
                "actif. state_confirmed=true seulement si l'onglet actif pointe "
                "bien vers le domaine demande."
            ),
        )
        @self._journaled("browse_open_url", "url", self._journal_host)
        @self._desktop_access
        async def browse_open_url(
            url: str,
            browser: str | None = None,
            new_tab: bool = True,
        ) -> dict:
            """Open a URL in a browser and verify the active tab."""
            debug_live(
                "tool_call",
                tool="browse_open_url",
                browser=browser,
                new_tab=new_tab,
            )
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.open_url,
                    url,
                    browser,
                    new_tab,
                )
            self._debug_browser_result("browse_open_url", result)
            return result.to_livekit_dict()

        @function_tool(
            name="browse_search_web",
            description=(
                "Lance une recherche web dans Safari ou Google Chrome puis relit "
                "l'onglet actif pour verifier. Utilise ce tool pour une demande "
                "comme cherche la meteo. engine accepte google, duckduckgo ou "
                "bing (google par defaut). command_executed ne prouve pas que les "
                "resultats sont charges ; state_confirmed le fait."
            ),
        )
        @self._journaled("browse_search_web")
        @self._desktop_access
        async def browse_search_web(
            query: str,
            browser: str | None = None,
            engine: str | None = None,
        ) -> dict:
            """Run a web search in a browser and verify the active tab."""
            debug_live(
                "tool_call",
                tool="browse_search_web",
                browser=browser,
                engine=engine,
                query_length=len(query) if isinstance(query, str) else None,
            )
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.search_web,
                    query,
                    browser,
                    engine,
                )
            self._debug_browser_result("browse_search_web", result)
            return result.to_livekit_dict()

        @function_tool(
            name="browse_get_active_tab",
            description=(
                "Lit l'onglet actif (URL et titre) de Safari ou Google Chrome. "
                "Utilise ce tool pour savoir quelle page est affichee au lieu de "
                "le deduire. browser=None choisit automatiquement le navigateur."
            ),
        )
        @self._desktop_access
        async def browse_get_active_tab(browser: str | None = None) -> dict:
            """Read the active tab of a browser."""
            debug_live("tool_call", tool="browse_get_active_tab", browser=browser)
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.get_active_tab,
                    browser,
                )
            self._debug_browser_result("browse_get_active_tab", result)
            return result.to_livekit_dict()

        @function_tool(
            name="browse_list_tabs",
            description=(
                "Liste les onglets ouverts (index, URL, titre) de la fenetre "
                "active de Safari ou Google Chrome. Utile avant d'activer un "
                "onglet precis. browser=None choisit automatiquement."
            ),
        )
        @self._desktop_access
        async def browse_list_tabs(browser: str | None = None) -> dict:
            """List the tabs of a browser's front window."""
            debug_live("tool_call", tool="browse_list_tabs", browser=browser)
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.list_tabs,
                    browser,
                )
            self._debug_browser_result("browse_list_tabs", result)
            return result.to_livekit_dict()

        @function_tool(
            name="browse_activate_tab",
            description=(
                "Active un onglet dans Safari ou Google Chrome, puis verifie "
                "qu'il est au premier plan. Deux modes exclusifs : fournis index, "
                "un entier (position de l'onglet telle que donnee par "
                "browse_list_tabs), pour l'activer directement et de maniere "
                "deterministe ; OU fournis query (texte) pour une recherche sur "
                "l'URL ou le titre. Quand l'utilisateur choisit explicitement un "
                "onglet par son numero ou sa position (par exemple le 8), utilise "
                "index, jamais query. Si query correspond a plusieurs onglets, le "
                "resultat est ambiguous_tab : ne choisis pas au hasard, relis "
                "browse_list_tabs et rappelle ce tool avec l'index voulu. "
                "browser=None choisit automatiquement."
            ),
        )
        @self._desktop_access
        async def browse_activate_tab(
            query: str | None = None,
            index: int | None = None,
            browser: str | None = None,
        ) -> dict:
            """Activate a tab by explicit index or by query, then verify it."""
            debug_live(
                "tool_call",
                tool="browse_activate_tab",
                browser=browser,
                index=index,
                query_length=len(query) if isinstance(query, str) else None,
            )
            async with self.browser_lock:
                result = await asyncio.to_thread(
                    self.browser.activate_tab,
                    query,
                    index,
                    browser,
                )
            self._debug_browser_result("browse_activate_tab", result)
            return result.to_livekit_dict()

        @function_tool(
            name="capture_screen",
            description=(
                "Prend une capture d'ecran complete et l'enregistre dans un "
                "fichier PNG, puis relit le fichier pour confirmer "
                "l'enregistrement. Utilise ce tool quand l'utilisateur demande "
                "une capture d'ecran. path=None genere un nom horodate dans le "
                "dossier des captures ; display cible un ecran precis (1 par "
                "defaut). state_confirmed=true seulement si le fichier existe et "
                "n'est pas vide. Le resultat ne contient pas l'image, seulement "
                "son chemin et sa taille."
            ),
        )
        @self._journaled("capture_screen")
        @self._desktop_access
        async def capture_screen(
            path: str | None = None,
            display: int | None = None,
        ) -> dict:
            """Capture the full screen to a PNG file and verify it."""
            debug_live("tool_call", tool="capture_screen", display=display)
            async with self.screenshot_lock:
                result = await asyncio.to_thread(
                    self.screenshot.capture_screen,
                    path,
                    display,
                )
            self._debug_screenshot_result("capture_screen", result)
            return result.to_livekit_dict()

        @function_tool(
            name="capture_region",
            description=(
                "Prend une capture d'une region rectangulaire de l'ecran "
                "(x, y, largeur, hauteur en points, origine en haut a gauche) et "
                "l'enregistre en PNG, puis verifie le fichier. N'invente jamais "
                "de coordonnees : utilise ce tool uniquement avec une region "
                "fournie par l'utilisateur ou par un tool fiable. state_confirmed "
                "=true seulement si le fichier a bien ete ecrit."
            ),
        )
        @self._journaled("capture_region")
        @self._desktop_access
        async def capture_region(
            x: int,
            y: int,
            width: int,
            height: int,
            path: str | None = None,
        ) -> dict:
            """Capture a rectangular region to a PNG file and verify it."""
            debug_live(
                "tool_call",
                tool="capture_region",
                width=width,
                height=height,
            )
            async with self.screenshot_lock:
                result = await asyncio.to_thread(
                    self.screenshot.capture_region,
                    x,
                    y,
                    width,
                    height,
                    path,
                )
            self._debug_screenshot_result("capture_region", result)
            return result.to_livekit_dict()

        @function_tool(
            name="capture_window",
            description=(
                "Prend une capture de la fenetre active, ou de la fenetre d'une "
                "application nommee (elle est d'abord mise au premier plan et "
                "verifiee), puis enregistre un PNG et relit le fichier. Utilise ce "
                "tool pour capturer une fenetre precise. Si la fenetre active ne "
                "correspond pas a l'application demandee, la capture est arretee "
                "(active_window_mismatch)."
            ),
        )
        @self._journaled("capture_window", "app_name")
        @self._desktop_access
        async def capture_window(
            app_name: str | None = None,
            path: str | None = None,
        ) -> dict:
            """Capture the active or a named window to a PNG file and verify it."""
            debug_live("tool_call", tool="capture_window", app_name=app_name)
            async with self.screenshot_lock:
                result = await asyncio.to_thread(
                    self.screenshot.capture_window,
                    app_name,
                    path,
                )
            self._debug_screenshot_result("capture_window", result)
            return result.to_livekit_dict()

        @function_tool(
            name="describe_screen",
            description=(
                "Regarde l'ecran et decrit ce qui est visible. Capture (fenetre "
                "active par defaut, ou tout l'ecran avec target='screen') puis "
                "analyse l'image avec un modele multimodal, et renvoie une "
                "description. Utilise ce tool pour une demande comme qu'est-ce "
                "qu'il y a sur mon ecran. Rapporte seulement ce que l'analyse "
                "renvoie ; n'invente rien. Ce tool observe uniquement : il ne "
                "fournit aucune coordonnee et ne declenche aucune action. Pour "
                "cliquer ou taper, utilise Accessibility, jamais ce tool."
            ),
        )
        @self._journaled('describe_screen')
        @self._desktop_access
        async def describe_screen(
            target: str = "window",
            app_name: str | None = None,
        ) -> dict:
            """Capture then describe what is visible (read-only)."""
            guard = self._vision_guard("describe_screen")
            if guard is not None:
                return guard
            debug_live("tool_call", tool="describe_screen", source=target)
            async with self.vision_lock:
                result = await asyncio.to_thread(
                    self.vision.describe_screen,
                    target,
                    app_name,
                )
            self._debug_vision_result("describe_screen", result)
            return result.to_livekit_dict()

        @function_tool(
            name="ask_about_screen",
            description=(
                "Regarde l'ecran et repond a une question sur ce qui est affiche "
                "(par exemple quelle temperature / quel prix est affiche, que dit "
                "cette page). Capture (fenetre active par defaut, ou tout l'ecran "
                "avec target='screen') puis analyse l'image. Si l'information "
                "n'est pas visible ou lisible, dis-le, n'invente jamais une "
                "valeur. Ce tool observe uniquement : aucune coordonnee, aucune "
                "action. Pour agir, utilise Accessibility."
            ),
        )
        @self._journaled('ask_about_screen')
        @self._desktop_access
        async def ask_about_screen(
            question: str,
            target: str = "window",
            app_name: str | None = None,
        ) -> dict:
            """Capture then answer a question about the screen (read-only)."""
            guard = self._vision_guard("ask_about_screen")
            if guard is not None:
                return guard
            debug_live(
                "tool_call",
                tool="ask_about_screen",
                source=target,
                question_length=len(question) if isinstance(question, str) else None,
            )
            async with self.vision_lock:
                result = await asyncio.to_thread(
                    self.vision.ask_about_screen,
                    question,
                    target,
                    app_name,
                )
            self._debug_vision_result("ask_about_screen", result)
            return result.to_livekit_dict()

        @function_tool(
            name="read_whatsapp_conversation",
            description=(
                "Lit et resume la conversation WhatsApp actuellement OUVERTE en la "
                "regardant (vision). Opt-in : utilise ce tool uniquement quand "
                "l'utilisateur demande explicitement de lire/resumer ses messages "
                "WhatsApp ('lis ma conversation', 'qu'est-ce qu'on m'a ecrit sur "
                "WhatsApp', 'resume cette discussion'). Il met WhatsApp au premier "
                "plan puis analyse l'ecran ; rapporte seulement ce qui est lu, sans "
                "inventer. Pour repondre ensuite, utilise prepare_send_message (envoi "
                "confirme). question : une question precise optionnelle sur la "
                "conversation."
            ),
        )
        @self._journaled("read_whatsapp_conversation")
        @self._desktop_access
        async def read_whatsapp_conversation(question: str | None = None) -> dict:
            """Read the open WhatsApp conversation via vision (opt-in)."""
            guard = self._vision_guard("read_whatsapp_conversation")
            if guard is not None:
                return guard
            debug_live("tool_call", tool="read_whatsapp_conversation")
            await asyncio.to_thread(self.windows.focus_window, "WhatsApp")
            await asyncio.sleep(self.messaging.search_settle_seconds)
            prompt = question.strip() if isinstance(question, str) and question.strip() else (
                "Resume la conversation WhatsApp ouverte : indique avec qui, et les "
                "derniers messages echanges. Rapporte seulement ce qui est lisible."
            )
            async with self.vision_lock:
                result = await asyncio.to_thread(
                    self.vision.ask_about_screen, prompt, "window", "WhatsApp",
                )
            self._debug_vision_result("read_whatsapp_conversation", result)
            return result.to_livekit_dict()

        @function_tool(
            name="search_the_web",
            description=(
                "Cherche une information a jour sur le web et la synthetise a voix "
                "haute : actualites, meteo, prix, cours, resultats, 'qui est', 'quelles "
                "sont les nouvelles', 'quoi de neuf sur X'. La recherche tourne en "
                "arriere-plan (quelques secondes) ; des que tu appelles ce tool, dis a "
                "l'utilisateur que tu regardes, puis le resultat sera annonce tout seul. "
                "Si l'utilisateur ne precise pas de domaine pour 'les nouvelles', ne "
                "bloque pas : prends les grands titres a la une et propose d'affiner. "
                "N'utilise pas ce tool pour agir sur le Mac ni pour une question dont la "
                "reponse ne depend pas d'une information actuelle. question : la question "
                "complete en francais."
            ),
        )
        @self._journaled("search_the_web")
        async def search_the_web(question: str) -> dict:
            """Start a background web search; its result is announced by voice."""
            debug_live(
                "tool_call",
                tool="search_the_web",
                question_length=len(question) if isinstance(question, str) else None,
            )
            if not isinstance(question, str) or not question.strip():
                return ToolResult.failure(
                    action="search_the_web",
                    message="La question de recherche est vide.",
                    error_code="invalid_question",
                ).to_livekit_dict()
            if self._web_running():
                return ToolResult.failure(
                    action="search_the_web",
                    message="Une recherche web est deja en cours ; attends son resultat.",
                    error_code="web_search_running",
                ).to_livekit_dict()
            self._web_task = asyncio.get_running_loop().create_task(
                self._run_web_search(question.strip())
            )
            return ToolResult.success(
                action="search_the_web",
                message=(
                    "Recherche lancee. Dis simplement a l'utilisateur que tu regardes ; "
                    "le resultat sera annonce dans un instant."
                ),
                search_started=True,
            ).to_livekit_dict()

        @function_tool(
            name="summarize_url",
            description=(
                "Lit une page web dont l'utilisateur donne l'adresse et la resume ou "
                "repond a une question a son sujet : 'resume cette page', 'que dit "
                "cet article sur ...'. url : l'adresse http/https ; question : une "
                "demande precise optionnelle. N'utilise que des URL fournies par "
                "l'utilisateur."
            ),
        )
        @self._journaled("summarize_url")
        async def summarize_url(url: str, question: str | None = None) -> dict:
            """Fetch a user-provided URL and summarize/answer from its content."""
            debug_live("tool_call", tool="summarize_url")
            result = await asyncio.to_thread(self.webread.summarize_url, url, question)
            self._debug_tool_result("summarize_url", result)
            return result.to_livekit_dict()

        @function_tool(
            name="morning_briefing",
            description=(
                "Prepare un point du jour parle : la date, un apercu de l'agenda et "
                "les principales actualites. Pour 'fais-moi le point', 'briefing du "
                "matin', 'quoi de neuf aujourd'hui'. Tourne en arriere-plan : des que "
                "tu l'appelles, dis que tu prepares le point ; le resultat sera "
                "annonce tout seul. topic : theme d'actualite optionnel."
            ),
        )
        @self._journaled("morning_briefing")
        async def morning_briefing(topic: str | None = None) -> dict:
            """Start a background briefing (date + agenda + news), announced by voice."""
            debug_live("tool_call", tool="morning_briefing")
            if self._briefing_running():
                return ToolResult.failure(
                    action="morning_briefing",
                    message="Un briefing est deja en cours de preparation.",
                    error_code="briefing_running",
                ).to_livekit_dict()
            self._briefing_task = asyncio.get_running_loop().create_task(
                self._run_briefing(topic)
            )
            return ToolResult.success(
                action="morning_briefing",
                message=(
                    "Briefing en preparation. Dis a l'utilisateur que tu prepares le "
                    "point du jour ; le resultat sera annonce dans un instant."
                ),
                briefing_started=True,
            ).to_livekit_dict()

        @function_tool(
            name="web_answer",
            description=(
                "Recherche une information a jour sur le web et renvoie une reponse "
                "synthetisee avec ses sources. Outil reserve aux taches longues : il "
                "BLOQUE le temps de la recherche (quelques secondes). Appuie-toi "
                "uniquement sur sa reponse et ses sources, n'invente rien. question : "
                "la question complete en francais."
            ),
        )
        @self._journaled("web_answer")
        async def web_answer(question: str) -> dict:
            """Blocking web search for the planner (not exposed to the voice model)."""
            debug_live(
                "tool_call",
                tool="web_answer",
                question_length=len(question) if isinstance(question, str) else None,
            )
            result = await asyncio.to_thread(self.knowledge.answer, question)
            return result.to_livekit_dict()

        @function_tool(
            name="run_task",
            description=(
                "Confie a Jarvis une TACHE LONGUE en plusieurs etapes qui demande "
                "de chercher, verifier et enchainer plusieurs actions (par exemple : "
                "retrouve le dernier PDF telecharge, renomme-le et range-le dans "
                "Documents). La tache tourne en arriere-plan avec un planificateur "
                "local plus lent (souvent une minute) ; le resultat sera annonce a la "
                "fin. N'utilise PAS ce tool pour une demande simple ou un enchainement "
                "court que tu peux faire directement avec tes autres tools (volume, "
                "media, ouvrir une app ou un site, envoyer un message). goal : "
                "l'objectif complet et autonome, en francais. read_only=true pour une recherche sans action sur le Mac ; seuls les outils de lecture autorises seront disponibles. Sinon la mission reserve le bureau et attend son tour. Jusqu'a deux missions executent en parallele, six demandes actives maximum. Le retour contient task_id. after_id optionnel lance cette mission seulement apres le statut completed d’une mission existante ; echec, annulation ou accord vocal requis bloquent la suite sans action. Aucun resultat ni argument n’est automatiquement recopie entre missions."
            ),
        )
        @self._journaled("run_task")
        async def run_task(goal: str, read_only: bool = False, after_id: str | None = None) -> dict:
            """Start a multi-step planner task in the background."""
            debug_live(
                "tool_call",
                tool="run_task",
                goal_length=len(goal) if isinstance(goal, str) else None,
            )
            return self.tasks.start(goal, read_only=read_only, after_id=after_id)

        @function_tool(
            name="task_status",
            description=(
                "Donne l'avancement de la tache en arriere-plan (en cours, nombre "
                "d'etapes, duree) ou le resultat de la derniere tache. Utilise ce "
                "tool pour 'ou en est la tache', 'c'est bientot fini ?'. Sans task_id, liste les missions. Avec task_id, cible exactement cette mission."
            ),
        )
        async def task_status(task_id: str | None = None) -> dict:
            """Report the background task progress or last result."""
            debug_live("tool_call", tool="task_status")
            return self.tasks.status(task_id)

        @function_tool(
            name="cancel_task",
            description=(
                "Annule la tache en arriere-plan quand l'utilisateur dit stop, "
                "annule ou laisse tomber pendant qu'une tache tourne. Elle s'arrete "
                "avant l'etape suivante. Fournis task_id si plusieurs missions sont actives. Sans identifiant et avec plusieurs missions, demande laquelle annuler ; ne devine jamais."
            ),
        )
        @self._journaled("cancel_task")
        async def cancel_task(task_id: str | None = None) -> dict:
            """Request cancellation of the running background task."""
            debug_live("tool_call", tool="cancel_task")
            return self.tasks.cancel(task_id)

        @function_tool(
            name="save_task_procedure",
            description=(
                "Retient la DERNIERE tache reussie comme procedure reutilisable "
                "sous un nom (par exemple 'preparer ma reunion'), pour pouvoir "
                "dire ensuite 'refais comme d'habitude'. N'enregistre que "
                "l'enchainement des outils, jamais le contenu. Utilise ce tool "
                "quand l'utilisateur dit 'retiens cette tache' ou 'garde ca comme "
                "procedure'. S'il n'y a pas de tache reussie recente, dis-le."
            ),
        )
        @self._journaled("save_task_procedure", target_arg="name")
        async def save_task_procedure(name: str) -> dict:
            """Learn the last successful task as a named, reusable procedure."""
            debug_live("tool_call", tool="save_task_procedure")
            last = self.tasks.last_completed()
            if last is None:
                return ToolResult.failure(
                    action="save_task_procedure",
                    message="Aucune tache recente reussie a retenir comme procedure.",
                    error_code="no_completed_task",
                ).to_livekit_dict()
            _goal, tool_names = last
            steps = [{"tool": name_, "target": None} for name_ in tool_names]
            async with self.memory_lock:
                result = await asyncio.to_thread(
                    self.memory.save_procedure, name, steps, "user",
                )
            self._debug_tool_result("save_task_procedure", result)
            return result.to_livekit_dict()

        @function_tool(
            name="run_procedure",
            description=(
                "Rejoue une procedure enregistree par son nom (par exemple 'refais "
                "comme d'habitude pour preparer ma reunion'). Charge l'enchainement "
                "habituel et lance une tache en arriere-plan qui l'adapte et verifie "
                "chaque etape. Si aucune procedure ne porte ce nom, dis-le sans rien "
                "lancer."
            ),
        )
        @self._journaled("run_procedure", target_arg="name")
        async def run_procedure(name: str) -> dict:
            """Replay a saved procedure as a background task seeded by its steps."""
            debug_live("tool_call", tool="run_procedure")
            async with self.memory_lock:
                got = await asyncio.to_thread(self.memory.get_procedure, name)
            if not got.ok:
                return got.to_livekit_dict()
            steps = got.data.get("procedure", {}).get("steps") or []
            skeleton = ", ".join(
                step["tool"] for step in steps if isinstance(step, dict) and step.get("tool")
            )
            goal = (
                f"Refais la procedure habituelle « {name} ». Enchainement habituel "
                f"des outils (adapte si besoin et verifie chaque etape) : {skeleton}."
            )
            return self.tasks.start(goal)

        @function_tool(
            name="save_macro",
            description=(
                "Enregistre une MACRO : un workflow reutilisable defini a l'avance "
                "par un nom et un objectif en langage naturel ('enregistre une macro "
                "reunion : ouvre Zoom et prepare un message a l'equipe'). name : le "
                "nom court ; goal : l'objectif complet. Pour la lancer ensuite, "
                "run_macro. Differe des procedures (apprises apres une tache reussie)."
            ),
        )
        @self._journaled("save_macro", "name")
        async def save_macro(name: str, goal: str) -> dict:
            """Save a named goal macro."""
            debug_live("tool_call", tool="save_macro")
            try:
                row = await asyncio.to_thread(self.macro_store.save, name, goal)
            except MacroError as error:
                return ToolResult.failure(
                    action="save_macro", message=error.message, error_code=error.code,
                ).to_livekit_dict()
            return ToolResult.success(
                action="save_macro", message=f"Macro « {row['name']} » enregistree.",
                name=row["name"],
            ).to_livekit_dict()

        @function_tool(
            name="run_macro",
            description=(
                "Lance une macro enregistree par son nom ('lance la macro reunion'). "
                "Demarre une tache en arriere-plan avec l'objectif de la macro. Si "
                "aucune macro ne porte ce nom, le dit sans rien lancer."
            ),
        )
        @self._journaled("run_macro", "name")
        async def run_macro(name: str) -> dict:
            """Run a saved macro as a background planner task."""
            debug_live("tool_call", tool="run_macro")
            macro = await asyncio.to_thread(self.macro_store.get, name)
            if macro is None:
                return ToolResult.failure(
                    action="run_macro",
                    message=f"Aucune macro nommee « {name} ».",
                    error_code="macro_not_found",
                ).to_livekit_dict()
            return self.tasks.start(macro["goal"])

        @function_tool(
            name="list_macros",
            description="Liste les macros enregistrees (nom et objectif).",
        )
        async def list_macros() -> dict:
            """List saved macros."""
            debug_live("tool_call", tool="list_macros")
            rows = await asyncio.to_thread(self.macro_store.list)
            macros = [{"name": r["name"], "goal": r["goal"]} for r in rows]
            return ToolResult.success(
                action="list_macros", message=f"{len(macros)} macro(s) enregistree(s).",
                macros=macros, count=len(macros),
            ).to_livekit_dict()

        @function_tool(
            name="delete_macro",
            description="Supprime une macro enregistree par son nom.",
        )
        @self._journaled("delete_macro", "name")
        async def delete_macro(name: str) -> dict:
            """Delete a saved macro."""
            debug_live("tool_call", tool="delete_macro")
            deleted = await asyncio.to_thread(self.macro_store.delete, name)
            if not deleted:
                return ToolResult.failure(
                    action="delete_macro", message=f"Aucune macro nommee « {name} ».",
                    error_code="macro_not_found",
                ).to_livekit_dict()
            return ToolResult.success(
                action="delete_macro", message=f"Macro « {name} » supprimee.", name=name,
            ).to_livekit_dict()

        @function_tool(
            name="remember_context",
            description=(
                "Note en une phrase ce sur quoi vous travaillez, pour pouvoir "
                "reprendre plus tard, meme dans une autre session ('retiens ou on "
                "en est', ou de toi-meme a un point d'etape). text : un court resume "
                "de l'etat d'avancement. Different de remember (faits durables) et "
                "de save_note (notes dictees)."
            ),
        )
        @self._journaled("remember_context")
        async def remember_context(text: str) -> dict:
            """Record a rolling conversation-context note."""
            debug_live("tool_call", tool="remember_context")
            try:
                row = await asyncio.to_thread(self.context_store.add, text)
            except ContextError as error:
                return ToolResult.failure(
                    action="remember_context", message=error.message, error_code=error.code,
                ).to_livekit_dict()
            return ToolResult.success(
                action="remember_context", message="Contexte retenu.", context_id=row["id"],
            ).to_livekit_dict()

        @function_tool(
            name="recall_context",
            description=(
                "Rappelle ce sur quoi vous travailliez recemment, pour reprendre le "
                "fil ('reprends ou on en etait', 'on faisait quoi deja'). Renvoie les "
                "dernieres notes de contexte."
            ),
        )
        async def recall_context() -> dict:
            """Return recent conversation-context notes."""
            debug_live("tool_call", tool="recall_context")
            rows = await asyncio.to_thread(self.context_store.recent)
            entries = [r["text"] for r in rows]
            if entries:
                message = "Voici ou on en etait : " + " ; ".join(entries)
            else:
                message = "Je n'ai pas encore de contexte recent enregistre."
            return ToolResult.success(
                action="recall_context", message=message, context=entries, count=len(entries),
            ).to_livekit_dict()

        @function_tool(
            name="schedule_message",
            description=(
                "PLANIFIE l'envoi d'un message a un destinataire a une date/heure "
                "future, SANS l'envoyer maintenant. Utilise ce tool quand "
                "l'utilisateur dit 'envoie X a Marie demain a 9h', 'programme un "
                "message pour ce soir'. Calcule when comme une date/heure absolue au "
                "format ISO 8601 (par exemple 2026-10-16T09:00) a partir de l'heure "
                "actuelle. Comme tout envoi, ce tool renvoie un token et "
                "requires_confirmation : annonce a l'utilisateur l'application, le "
                "destinataire, le contenu et l'heure, puis attends un oui clair avant "
                "confirm_action(token). Le message partira tout seul a l'heure dite si "
                "le Mac est allume, deverrouille et WhatsApp lance ; le destinataire "
                "sera revérifie a ce moment-la. app_name par defaut WhatsApp. "
                "repeat : 'none' (defaut), 'daily' ou 'weekly' pour un envoi recurrent."
            ),
        )
        @self._journaled("schedule_message", "app_name")
        async def schedule_message(
            recipient: str,
            text: str,
            when: str,
            app_name: str = "WhatsApp",
            repeat: str = "none",
        ) -> dict:
            """Register a future send for confirmation; nothing is scheduled yet."""
            debug_live(
                "tool_call",
                tool="schedule_message",
                app_name=app_name,
                text_length=len(text) if isinstance(text, str) else None,
            )
            if not isinstance(text, str) or not text.strip():
                return ToolResult.failure(
                    action="schedule_message",
                    message="Le message a planifier est obligatoire.",
                    error_code="invalid_text",
                ).to_livekit_dict()
            if not isinstance(recipient, str) or not recipient.strip():
                return ToolResult.failure(
                    action="schedule_message",
                    message="Le destinataire est obligatoire.",
                    error_code="invalid_recipient",
                ).to_livekit_dict()
            try:
                due_at = parse_due_at(when)
            except ScheduleError as error:
                return ToolResult.failure(
                    action="schedule_message",
                    message=error.message,
                    error_code=error.code,
                ).to_livekit_dict()
            recurrence = (repeat or "none").strip().lower()
            if recurrence not in ("none", "daily", "weekly"):
                return ToolResult.failure(
                    action="schedule_message",
                    message="La recurrence doit etre none, daily ou weekly.",
                    error_code="invalid_recurrence",
                ).to_livekit_dict()

            # Apply memory locally: "ma mere" -> stored contact name.
            async with self.memory_lock:
                resolved = await asyncio.to_thread(self.memory.resolve_person, recipient)
            target_recipient = resolved or recipient.strip()

            def _executor():
                row = self.schedule_store.add(
                    app_name, target_recipient, text, due_at, recurrence,
                )
                return ToolResult.success(
                    action="schedule_message",
                    message="Message planifie.",
                    scheduled_id=row["id"],
                    recipient=row["recipient"],
                    due_at=row["due_at"],
                    app=row["app"],
                    recurrence=row["recurrence"],
                )

            async with self.confirmation_lock:
                token = self.pending_actions.register("schedule_message", _executor)
            return ToolResult.success(
                action="schedule_message",
                message=(
                    "Envoi planifie a confirmer. Annonce le destinataire, le contenu "
                    "et l'heure, puis attends la confirmation avant confirm_action."
                ),
                requires_confirmation=True,
                token=token,
                target_app=app_name,
                due_at=due_at,
                text_length=len(text),
                recurrence=recurrence,
                recipient_from_memory=bool(resolved),
            ).to_livekit_dict()

        @function_tool(
            name="list_scheduled_messages",
            description=(
                "Liste les messages planifies en attente d'envoi (id, destinataire, "
                "heure prevue, contenu). Utilise ce tool pour 'quels messages sont "
                "programmes', 'qu'est-ce que tu dois envoyer plus tard'."
            ),
        )
        async def list_scheduled_messages() -> dict:
            """Return pending scheduled messages."""
            debug_live("tool_call", tool="list_scheduled_messages")
            rows = await asyncio.to_thread(self.schedule_store.list, "pending")
            sending = await asyncio.to_thread(self.schedule_store.list, "sending")
            failed = await asyncio.to_thread(self.schedule_store.list, "failed")
            review = sending + [row for row in failed if (row.get("last_error") or "").startswith("envoi incertain")]
            review_items = [{"id": row["id"], "recipient": row["recipient"],
                             "status": row["status"], "reason": row.get("last_error") or "Envoi en cours ou interrompu : resultat a verifier."}
                            for row in review]
            messages = [
                {
                    "id": row["id"],
                    "app": row["app"],
                    "recipient": row["recipient"],
                    "due_at": row["due_at"],
                    "text": row["text"],
                }
                for row in rows
            ]
            return ToolResult.success(
                action="list_scheduled_messages",
                message=f"{len(messages)} message(s) planifie(s) en attente. {len(review_items)} envoi(s) a verifier ; aucune relance automatique pour ceux-ci.",
                scheduled=messages,
                count=len(messages),
                requires_review=review_items,
                review_count=len(review_items),
            ).to_livekit_dict()

        @function_tool(
            name="cancel_scheduled_message",
            description=(
                "Annule un message planifie par son id (obtenu via "
                "list_scheduled_messages). Utilise ce tool pour 'annule le message "
                "prevu pour Marie', 'ne l'envoie finalement pas'."
            ),
        )
        @self._journaled("cancel_scheduled_message")
        async def cancel_scheduled_message(message_id: int) -> dict:
            """Cancel a still-pending scheduled message."""
            debug_live("tool_call", tool="cancel_scheduled_message")
            cancelled = await asyncio.to_thread(self.schedule_store.cancel, message_id)
            if not cancelled:
                return ToolResult.failure(
                    action="cancel_scheduled_message",
                    message="Aucun message planifie en attente avec cet id.",
                    error_code="scheduled_message_not_found",
                ).to_livekit_dict()
            return ToolResult.success(
                action="cancel_scheduled_message",
                message="Message planifie annule.",
                scheduled_id=message_id,
            ).to_livekit_dict()

        @function_tool(
            name="set_reminder",
            description=(
                "Programme un RAPPEL personnel qui declenchera une notification "
                "macOS a l'heure dite ('rappelle-moi dans 20 minutes de sortir le "
                "gateau', 'rappelle-moi demain a 8h d'appeler le dentiste'). Calcule "
                "when comme une date/heure absolue ISO 8601 a partir de l'heure "
                "actuelle. C'est une note a soi-meme (aucun envoi exterieur), donc "
                "pas de confirmation : le rappel est enregistre directement. Il se "
                "declenche si le Mac est allume a ce moment-la. repeat : 'none' "
                "(defaut), 'daily' ou 'weekly' pour un rappel recurrent."
            ),
        )
        @self._journaled("set_reminder")
        async def set_reminder(text: str, when: str, repeat: str = "none") -> dict:
            """Store a personal reminder that fires a macOS notification."""
            debug_live("tool_call", tool="set_reminder", text_length=len(text) if isinstance(text, str) else None)
            if not isinstance(text, str) or not text.strip():
                return ToolResult.failure(
                    action="set_reminder",
                    message="Le texte du rappel est obligatoire.",
                    error_code="invalid_text",
                ).to_livekit_dict()
            try:
                due_at = parse_due_at(when)
            except ScheduleError as error:
                return ToolResult.failure(
                    action="set_reminder", message=error.message, error_code=error.code,
                ).to_livekit_dict()
            try:
                row = await asyncio.to_thread(self.reminder_store.add, text, due_at, repeat)
            except ReminderError as error:
                return ToolResult.failure(
                    action="set_reminder", message=error.message, error_code=error.code,
                ).to_livekit_dict()
            return ToolResult.success(
                action="set_reminder",
                message="Rappel enregistre.",
                reminder_id=row["id"],
                due_at=row["due_at"],
                recurrence=row["recurrence"],
            ).to_livekit_dict()

        @function_tool(
            name="list_reminders",
            description=(
                "Liste les rappels personnels en attente (id, heure, texte). Pour "
                "'quels rappels j'ai', 'qu'est-ce que tu dois me rappeler'."
            ),
        )
        async def list_reminders() -> dict:
            """Return pending reminders."""
            debug_live("tool_call", tool="list_reminders")
            rows = await asyncio.to_thread(self.reminder_store.list, "pending")
            reminders = [
                {"id": r["id"], "due_at": r["due_at"], "text": r["text"]} for r in rows
            ]
            return ToolResult.success(
                action="list_reminders",
                message=f"{len(reminders)} rappel(s) en attente.",
                reminders=reminders,
                count=len(reminders),
            ).to_livekit_dict()

        @function_tool(
            name="cancel_reminder",
            description=(
                "Annule un rappel par son id (obtenu via list_reminders). Pour "
                "'annule le rappel du dentiste', 'oublie ce rappel'."
            ),
        )
        @self._journaled("cancel_reminder")
        async def cancel_reminder(reminder_id: int) -> dict:
            """Cancel a pending reminder."""
            debug_live("tool_call", tool="cancel_reminder")
            cancelled = await asyncio.to_thread(self.reminder_store.cancel, reminder_id)
            if not cancelled:
                return ToolResult.failure(
                    action="cancel_reminder",
                    message="Aucun rappel en attente avec cet id.",
                    error_code="reminder_not_found",
                ).to_livekit_dict()
            return ToolResult.success(
                action="cancel_reminder",
                message="Rappel annule.",
                reminder_id=reminder_id,
            ).to_livekit_dict()

        @function_tool(
            name="privacy_overview",
            description=(
                "Donne un apercu de ce que Jarvis garde sur l'utilisateur : nombre "
                "de souvenirs, d'actions recentes au journal, de messages planifies "
                "et de rappels en attente. Pour 'qu'est-ce que tu sais sur moi', "
                "'qu'est-ce que tu gardes'. Pour voir le detail, utilise "
                "list_memories, list_scheduled_messages, list_reminders ou "
                "recent_activity ; pour effacer, forget."
            ),
        )
        async def privacy_overview() -> dict:
            """Aggregate what Jarvis stores, read-only."""
            debug_live("tool_call", tool="privacy_overview")
            async with self.memory_lock:
                mem = await asyncio.to_thread(self.memory.list_memories)
                act = await asyncio.to_thread(self.memory.recent_activity, 50)
                missions = await asyncio.to_thread(self.memory.recent_missions, 100)
            scheduled = await asyncio.to_thread(self.schedule_store.list, "pending")
            reminders = await asyncio.to_thread(self.reminder_store.list, "pending")
            checklists_count = 0
            store = checklist_store(self)
            if store.path.exists():
                overview = await asyncio.to_thread(store.manage, 'list')
                checklists_count = len(overview.data.get('lists', [])) if overview.ok else 0
            memory_count = mem.data.get("count", 0) if mem.ok else 0
            activity_count = len(act.data.get("episodes", [])) if act.ok else 0
            mission_count = missions.data.get("count", 0) if missions.ok else 0
            return ToolResult.success(
                action="privacy_overview",
                message=(
                    f"Je garde {memory_count} souvenir(s), {len(scheduled)} message(s) "
                    f"planifie(s) et {len(reminders)} rappel(s) en attente ; "
                    f"{activity_count} action(s) recente(s) au journal ; "
                    f"{mission_count} mission(s) dans l'historique ; {checklists_count} checklist(s) locale(s)."
                ),
                memory_count=memory_count,
                activity_count=activity_count,
                mission_count=mission_count,
                scheduled_count=len(scheduled),
                reminder_count=len(reminders),
                checklists_count=checklists_count,
            ).to_livekit_dict()

        @function_tool(
            name="clear_personal_data",
            description=(
                "EFFACE des donnees que Jarvis garde, apres confirmation. scope : "
                "'context' (notes de contexte de conversation), 'reminders' (rappels "
                "en attente), 'scheduled' (messages planifies en attente), 'missions' "
                "(historique des missions), ou 'all' (ces donnees et les checklists). "
                "scope checklists efface uniquement les checklists. Renvoie un token et requires_confirmation : annonce ce "
                "qui sera efface, puis confirm_action seulement sur un oui clair. Pour "
                "effacer un souvenir precis, utilise plutot forget."
            ),
        )
        @self._journaled("clear_personal_data", "scope")
        async def clear_personal_data(scope: str = "all") -> dict:
            """Prepare a confirmed purge of the data Jarvis stores."""
            debug_live("tool_call", tool="clear_personal_data", scope=scope)
            choice = (scope or "all").strip().lower()
            if choice not in ("context", "reminders", "scheduled", "checklists", "missions", "all"):
                return ToolResult.failure(
                    action="clear_personal_data",
                    message="scope doit etre context, reminders, scheduled, checklists, missions ou all.",
                    error_code="invalid_scope",
                ).to_livekit_dict()

            def _executor():
                return self._purge_personal_data(choice)

            async with self.confirmation_lock:
                token = self.pending_actions.register("clear_personal_data", _executor)
            return ToolResult.success(
                action="clear_personal_data",
                message=(
                    f"Effacement a confirmer ({choice}). Annonce ce qui sera efface, "
                    "puis attends la confirmation avant confirm_action."
                ),
                requires_confirmation=True,
                token=token,
                scope=choice,
            ).to_livekit_dict()

        @function_tool(
            name="enable_safe_mode",
            description=(
                "Active le mode securite (lecture seule) pour la session : Jarvis "
                "peut encore lire, chercher, analyser, prendre des notes et gerer "
                "ses propres rappels, mais toute action qui modifie le Mac ou "
                "envoie quelque chose vers l'exterieur (ouvrir/fermer une app, "
                "fichiers, presse-papiers, clavier/souris, mail, agenda, messages, "
                "navigation web, confirmation d'action, effacement) est bloquee. "
                "Utilise ce tool quand l'utilisateur demande 'passe en mode "
                "securite', 'mode lecture seule', 'ne touche a rien', 'mode sur'."
            ),
        )
        @self._journaled("enable_safe_mode")
        async def enable_safe_mode() -> dict:
            """Turn on session safe (read-only) mode."""
            debug_live("tool_call", tool="enable_safe_mode")
            already = self.read_only_mode
            self.read_only_mode = True
            return ToolResult.success(
                action="enable_safe_mode",
                message=(
                    "Mode securite deja actif." if already else
                    "Mode securite active : je reste en lecture seule et ne "
                    "modifie rien ni n'envoie rien tant qu'il est actif."
                ),
                read_only_mode=True,
                state_confirmed=True,
            ).to_livekit_dict()

        @function_tool(
            name="disable_safe_mode",
            description=(
                "Desactive le mode securite (lecture seule) et redonne a Jarvis "
                "l'acces complet a ses actions. Utilise ce tool quand l'utilisateur "
                "demande 'quitte le mode securite', 'reactive tout', 'desactive la "
                "lecture seule'."
            ),
        )
        @self._journaled("disable_safe_mode")
        async def disable_safe_mode() -> dict:
            """Turn off session safe (read-only) mode."""
            debug_live("tool_call", tool="disable_safe_mode")
            already = not self.read_only_mode
            self.read_only_mode = False
            return ToolResult.success(
                action="disable_safe_mode",
                message=(
                    "Le mode securite n'etait pas actif." if already else
                    "Mode securite desactive : je peux de nouveau agir sur le Mac "
                    "et preparer des envois, toujours avec les confirmations "
                    "habituelles."
                ),
                read_only_mode=False,
                state_confirmed=True,
            ).to_livekit_dict()

        tools = [
            enable_safe_mode,
            disable_safe_mode,
            set_volume,
            get_volume,
            open_app,
            close_app,
            is_app_running,
            play_pause,
            next_track,
            previous_track,
            get_media_state,
            get_battery_status,
            get_storage_status,
            get_system_info,
            self_check,
            run_shortcut,
            list_shortcuts,
            calculate,
            convert_units,
            save_note,
            list_notes,
            list_calendar_events,
            create_calendar_event,
            list_unread_emails,
            summarize_unread_emails,
            token_usage,
            token_usage_by_model,
            token_usage_by_project,
            token_usage_trend,
            compare_token_usage,
            recent_claude_sessions,
            system_snapshot,
            top_processes,
            system_usage_history,
            check_anomalies,
            run_claude_task,
            open_claude_session,
            draft_email,
            get_brightness,
            set_brightness,
            lock_screen,
            get_active_window,
            focus_window,
            minimize_window,
            maximize_window,
            move_window,
            arrange_windows,
            list_files,
            find_files,
            search_files_by_content,
            get_file_info,
            open_file,
            open_folder,
            create_folder,
            rename_file,
            move_file,
            get_clipboard_text,
            set_clipboard_text,
            clear_clipboard,
            rewrite_clipboard,
            type_text,
            press_key,
            hotkey,
            get_mouse_position,
            move_mouse,
            click,
            click_element,
            double_click,
            right_click,
            scroll,
            inspect_ui,
            find_ui_elements,
            focus_ui_element,
            activate_ui_element,
            select_all_and_copy,
            focus_app_ui_and_type,
            open_app_and_focus_ui,
            select_all_and_delete,
            send_prompt_to_app,
            prepare_send_message,
            confirm_action,
            cancel_action,
            remember,
            propose_memory,
            recall,
            list_memories,
            forget,
            recent_activity,
            recent_missions,
            browse_open_url,
            browse_search_web,
            browse_get_active_tab,
            browse_list_tabs,
            browse_activate_tab,
            capture_screen,
            capture_region,
            capture_window,
            describe_screen,
            ask_about_screen,
            ask_about_document,
            read_whatsapp_conversation,
            search_the_web,
            summarize_url,
            morning_briefing,
            send_last_web_result,
            schedule_message,
            list_scheduled_messages,
            cancel_scheduled_message,
            set_reminder,
            list_reminders,
            cancel_reminder,
            privacy_overview,
            run_task,
            task_status,
            cancel_task,
            save_task_procedure,
            run_procedure,
            save_macro,
            run_macro,
            list_macros,
            delete_macro,
            remember_context,
            recall_context,
            clear_personal_data,
        ]

        tools.append(dance_avatar)
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
        self.planner_tools = [tool for tool in tools if tool.info.name != "dance_avatar"] + [self._guard_read_only(web_answer)]
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
    )


