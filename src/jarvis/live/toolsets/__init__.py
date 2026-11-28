"""Voice tool groups of the Live registry.

Each module exposes ``build(registry) -> dict[name, tool]``. The tools are
closures over the registry (capabilities, locks, journal, pending actions),
exactly as when they were defined inline in ``ToolRegistry.livekit_tools``.
``VOICE_TOOL_ORDER`` fixes the order in which they are exposed to the model;
``tests/test_live_tool_catalog.py`` guards names, order and schemas.
"""
from typing import TYPE_CHECKING, Any

from jarvis.live.toolsets import (
    avatar_system,
    machine,
    office,
    usage,
    windows_files,
    input_devices,
    ui,
    messaging,
    memory_privacy,
    browser,
    screen,
    web,
    missions,
    schedule,
)

if TYPE_CHECKING:
    from jarvis.live.registry import ToolRegistry

GROUPS = (avatar_system, machine, office, usage,
          windows_files, input_devices, ui, messaging, memory_privacy,
          browser, screen, web, missions, schedule)

# Order of the core voice tools (before dance_avatar, productivity and
# extension tools, which ToolRegistry.livekit_tools appends after them).
VOICE_TOOL_ORDER: tuple[str, ...] = (
    "enable_safe_mode", "disable_safe_mode", "set_volume", "get_volume",
    "open_app", "close_app", "is_app_running", "play_pause", "next_track",
    "previous_track", "get_media_state", "get_battery_status",
    "get_storage_status", "get_system_info", "self_check", "run_shortcut",
    "list_shortcuts", "calculate", "convert_units", "save_note",
    "list_notes", "list_calendar_events", "create_calendar_event",
    "list_unread_emails", "summarize_unread_emails", "token_usage",
    "token_usage_by_model", "token_usage_by_project", "token_usage_trend",
    "compare_token_usage", "recent_claude_sessions", "system_snapshot",
    "top_processes", "system_usage_history", "check_anomalies",
    "run_claude_task", "open_claude_session", "draft_email",
    "get_brightness", "set_brightness", "lock_screen", "get_active_window",
    "focus_window", "minimize_window", "maximize_window", "move_window",
    "arrange_windows", "list_files", "find_files",
    "search_files_by_content", "get_file_info", "open_file", "open_folder",
    "create_folder", "rename_file", "move_file", "get_clipboard_text",
    "set_clipboard_text", "clear_clipboard", "rewrite_clipboard",
    "type_text", "press_key", "hotkey", "get_mouse_position", "move_mouse",
    "click", "click_element", "double_click", "right_click", "scroll",
    "inspect_ui", "find_ui_elements", "focus_ui_element",
    "activate_ui_element", "select_all_and_copy", "focus_app_ui_and_type",
    "open_app_and_focus_ui", "select_all_and_delete", "send_prompt_to_app",
    "prepare_send_message", "confirm_action", "cancel_action", "remember",
    "propose_memory", "recall", "list_memories", "forget",
    "recent_activity", "recent_missions", "browse_open_url",
    "browse_search_web", "browse_get_active_tab", "browse_list_tabs",
    "browse_activate_tab", "capture_screen", "capture_region",
    "capture_window", "describe_screen", "ask_about_screen",
    "describe_camera", "ask_about_document", "read_whatsapp_conversation",
    "search_the_web", "summarize_url", "morning_briefing",
    "send_last_web_result", "schedule_message", "list_scheduled_messages",
    "cancel_scheduled_message", "set_reminder", "list_reminders",
    "cancel_reminder", "privacy_overview", "run_task", "task_status",
    "cancel_task", "save_task_procedure", "run_procedure", "save_macro",
    "run_macro", "list_macros", "delete_macro", "remember_context",
    "recall_context", "clear_personal_data",
)

# Built like the voice tools but only handed to the planner.
PLANNER_ONLY_TOOLS: tuple[str, ...] = ("web_answer",)


def build_tools(registry: "ToolRegistry") -> dict[str, Any]:
    """Build every grouped tool, keyed by tool name."""
    tools: dict[str, Any] = {}
    for group in GROUPS:
        built = group.build(registry)
        overlap = tools.keys() & built.keys()
        if overlap:
            raise RuntimeError(f"duplicate Live tools: {sorted(overlap)}")
        tools.update(built)
    return tools
