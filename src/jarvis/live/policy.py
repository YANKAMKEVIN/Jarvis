"""Session policy constants shared by the Live tool registry."""



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
    # Session timers live in memory and only speak back to the user.
    "start_timer", "list_timers", "cancel_timer",
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
