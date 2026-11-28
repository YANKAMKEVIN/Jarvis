"""Capability wiring of the Live tool registry."""
import asyncio
from typing import Any

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.audio import AudioCapability
from jarvis.capabilities.browser import BrowserCapability
from jarvis.capabilities.calendar import CalendarCapability
from jarvis.capabilities.camera import CameraCapability
from jarvis.capabilities.claude_sessions import ClaudeSessionsCapability
from jarvis.capabilities.clipboard import ClipboardCapability
from jarvis.capabilities.compute import ComputeCapability
from jarvis.capabilities.diagnostics import DiagnosticsCapability
from jarvis.capabilities.document import DocumentCapability
from jarvis.capabilities.files import FilesCapability
from jarvis.capabilities.insights import InsightsCapability
from jarvis.capabilities.interaction import InteractionCapability
from jarvis.capabilities.keyboard import KeyboardCapability
from jarvis.capabilities.knowledge import KnowledgeCapability
from jarvis.capabilities.mail import MailCapability
from jarvis.capabilities.media import MediaCapability
from jarvis.capabilities.memory import MemoryCapability
from jarvis.capabilities.messaging import MessagingCapability
from jarvis.capabilities.mouse import MouseCapability
from jarvis.capabilities.notes import NotesCapability
from jarvis.capabilities.screenshot import ScreenshotCapability
from jarvis.capabilities.shortcuts import ShortcutsCapability
from jarvis.capabilities.system import SystemCapability
from jarvis.capabilities.system_metrics import SystemMetricsCapability
from jarvis.capabilities.text_workshop import TextWorkshopCapability
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.capabilities.usage import UsageCapability
from jarvis.capabilities.vision import VisionCapability
from jarvis.capabilities.webread import WebReadCapability
from jarvis.capabilities.windows import WindowCapability
from jarvis.context_store import ContextStore
from jarvis.insights.detector import InsightDetector
from jarvis.live.confirmation import PendingActionStore
from jarvis.macros import MacroStore
from jarvis.planner.resources import DesktopGate
from jarvis.planner.tasks import TaskManager
from jarvis.schedule.reminders import ReminderStore
from jarvis.schedule.store import ScheduledMessageStore


class RegistryCapabilities:
    """Wires every capability and store the Live tools act through.

    Each dependency can be injected (tests, desktop runtime); otherwise the
    default local implementation is built.
    """

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
