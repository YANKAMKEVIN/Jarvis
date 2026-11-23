"""Explicit effect of every Live tool, decided once when the tool is added.

`tests/test_tool_effects.py` requires each tool of the registry to appear in
exactly one family, and checks it against SAFE_MODE_ALLOWED:
- READ: observes only (the Mac, files, the web, Jarvis' stores). Always
  allowed in safe mode.
- LOCAL: writes only Jarvis' own private state (notes, memory, reminders,
  missions, captures in its folder, the safe-mode switch). Allowed or not,
  case by case.
- MAC: changes the Mac (apps, windows, files, keyboard, mouse, browser…).
  Never allowed in safe mode.
- OUTWARD: sends or may send something outside (messages, MCP calls,
  prompts to another assistant, confirmations). Never allowed in safe mode.
"""

READ = frozenset({
    "get_volume", "get_media_state", "get_battery_status", "get_system_info",
    "get_storage_status", "get_brightness", "self_check", "is_app_running",
    "list_shortcuts", "calculate", "convert_units",
    "list_files", "find_files", "search_files_by_content", "get_file_info", "ask_about_document",
    "get_active_window", "get_clipboard_text", "get_mouse_position", "inspect_ui", "find_ui_elements",
    "describe_screen", "ask_about_screen", "describe_camera",
    "list_calendar_events", "list_unread_emails", "summarize_unread_emails",
    "find_free_slots", "calendar_conflicts", "read_whatsapp_conversation",
    "list_notes", "search_notes", "read_note", "compare_documents", "extract_document_actions",
    "search_the_web", "summarize_url", "morning_briefing", "web_answer",
    "browse_get_active_tab", "browse_list_tabs",
    "recall", "list_memories", "recall_context", "list_reminders", "list_macros",
    "list_scheduled_messages", "list_timers",
    "token_usage", "token_usage_by_model", "token_usage_by_project", "token_usage_trend",
    "compare_token_usage", "recent_claude_sessions",
    "system_snapshot", "top_processes", "system_usage_history", "check_anomalies",
    "recent_activity", "recent_missions", "privacy_overview", "task_status",
    "list_mcp_tools", "list_skills", "use_skill",
})

LOCAL = frozenset({
    "enable_safe_mode", "disable_safe_mode", "dance_avatar",
    "capture_screen", "capture_region", "capture_window",
    "save_note", "append_note", "manage_checklist",
    "remember", "propose_memory", "forget", "remember_context",
    "set_reminder", "cancel_reminder", "cancel_scheduled_message",
    "save_macro", "delete_macro", "save_task_procedure",
    "run_task", "cancel_task", "pause_task", "resume_task", "cancel_action",
    "start_timer", "cancel_timer", "clear_personal_data",
})

MAC = frozenset({
    "set_volume", "open_app", "close_app", "play_pause", "next_track", "previous_track",
    "run_shortcut", "create_calendar_event", "draft_email", "run_claude_task", "open_claude_session",
    "set_brightness", "lock_screen",
    "focus_window", "minimize_window", "maximize_window", "move_window", "arrange_windows",
    "open_file", "open_folder", "create_folder", "rename_file", "move_file",
    "set_clipboard_text", "clear_clipboard", "rewrite_clipboard",
    "type_text", "press_key", "hotkey", "move_mouse", "click", "click_element", "double_click",
    "right_click", "scroll", "focus_ui_element", "activate_ui_element",
    "select_all_and_copy", "select_all_and_delete", "focus_app_ui_and_type", "open_app_and_focus_ui",
    "browse_open_url", "browse_search_web", "browse_activate_tab",
    "run_procedure", "run_macro",
})

OUTWARD = frozenset({
    "prepare_send_message", "send_last_web_result", "schedule_message", "send_prompt_to_app",
    "confirm_action", "call_mcp_tool",
})

FAMILIES = {"read": READ, "local": LOCAL, "mac": MAC, "outward": OUTWARD}


def effect_of(name: str) -> str | None:
    for family, names in FAMILIES.items():
        if name in names:
            return family
    return None
