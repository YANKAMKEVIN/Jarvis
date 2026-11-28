"""Shared fixtures of the Live POC tests: expected tool names, fake LiveKit pieces, security."""
from jarvis.security import SecurityDecision


EXPECTED_LIVE_TOOL_NAMES = sorted([
    "activate_ui_element",
    "arrange_windows",
    "disable_safe_mode",
    "enable_safe_mode",
    "list_mcp_tools", "call_mcp_tool", "list_skills", "use_skill",
    "summarize_unread_emails",
    "ask_about_document",
    "ask_about_screen",
    "describe_camera",
    "browse_activate_tab",
    "browse_get_active_tab",
    "browse_list_tabs",
    "browse_open_url",
    "browse_search_web",
    "calculate",
    "cancel_action",
    "cancel_reminder",
    "cancel_scheduled_message",
    "cancel_task",
    "capture_region",
    "capture_screen",
    "capture_window",
    "clear_clipboard",
    "clear_personal_data",
    "click",
    "click_element",
    "close_app",
    "confirm_action",
    "convert_units",
    "create_calendar_event",
    "create_folder",
    "dance_avatar",
    "delete_macro",
    "describe_screen",
    "double_click",
    "draft_email",
    "find_files",
    "find_ui_elements",
    "focus_app_ui_and_type",
    "focus_ui_element",
    "focus_window",
    "forget",
    "get_active_window",
    "get_battery_status",
    "get_brightness",
    "get_clipboard_text",
    "get_file_info",
    "get_media_state",
    "get_mouse_position",
    "get_storage_status",
    "get_system_info",
    "get_volume",
    "hotkey",
    "inspect_ui",
    "is_app_running",
    "list_calendar_events",
    "list_files",
    "list_macros",
    "list_memories",
    "list_notes",
    "list_reminders",
    "list_scheduled_messages",
    "list_shortcuts",
    "list_unread_emails",
    "lock_screen",
    "maximize_window",
    "minimize_window",
    "morning_briefing",
    "move_file",
    "move_mouse",
    "move_window",
    "next_track",
    "open_app",
    "open_app_and_focus_ui",
    "open_file",
    "open_folder",
    "play_pause",
    "prepare_send_message",
    "press_key",
    "previous_track",
    "privacy_overview",
    "propose_memory",
    "read_whatsapp_conversation",
    "recall",
    "recall_context",
    "recent_missions",
    "recent_activity",
    "token_usage",
    "token_usage_by_model",
    "token_usage_by_project",
    "token_usage_trend",
    "compare_token_usage",
    "recent_claude_sessions",
    "system_snapshot",
    "top_processes",
    "system_usage_history",
    "check_anomalies",
    "run_claude_task",
    "open_claude_session",
    "remember",
    "remember_context",
    "rename_file",
    "rewrite_clipboard",
    "right_click",
    "run_macro",
    "run_procedure",
    "run_shortcut",
    "run_task",
    "save_macro",
    "save_note",
    "save_task_procedure",
    "schedule_message",
    "scroll",
    "search_files_by_content",
    "search_the_web",
    "select_all_and_copy",
    "select_all_and_delete",
    "self_check",
    "send_last_web_result",
    "send_prompt_to_app",
    "set_brightness",
    "set_clipboard_text",
    "set_reminder",
    "set_volume",
    "summarize_url",
    "task_status",
    "type_text",
    "start_timer",
    "list_timers",
    "cancel_timer",
    "search_notes",
    "read_note",
    "append_note",
    "manage_checklist",
    "find_free_slots",
    "calendar_conflicts",
    "compare_documents",
    "extract_document_actions",
    "pause_task",
    "resume_task",
])


class FakeRealtime:
    def __init__(self):
        self.created = []

    def RealtimeModel(self, **kwargs):
        self.created.append(kwargs)
        return {
            "type": "realtime-model",
            "kwargs": kwargs,
        }


class FakeGoogle:
    def __init__(self):
        self.realtime = FakeRealtime()


class FakeAgentBase:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeJobContext:
    room = object()


class RecordingAgentSession:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.start_calls = []
        self.generate_reply_calls = []
        self.handlers = {}
        RecordingAgentSession.instances.append(self)

    def on(self, name, callback):
        self.handlers[name] = callback

    async def start(self, **kwargs):
        self.start_calls.append(kwargs)

    async def generate_reply(self, **kwargs):
        self.generate_reply_calls.append(kwargs)


class RecordingLiveSecurity:
    def __init__(self, allowed=True, requires_confirmation=False):
        self.allowed = allowed
        self.requires_confirmation = requires_confirmation
        self.intents = []

    def evaluate(self, intent):
        self.intents.append(intent)
        return SecurityDecision(
            allowed=self.allowed,
            requires_confirmation=self.requires_confirmation,
            reason="test security",
        )
