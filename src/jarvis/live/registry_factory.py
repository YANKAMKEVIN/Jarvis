"""Builds a ToolRegistry from low-level tools (security, macOS, filesystem...)."""
from typing import TYPE_CHECKING

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.audio import AudioCapability
from jarvis.capabilities.browser import BrowserCapability
from jarvis.capabilities.clipboard import ClipboardCapability
from jarvis.capabilities.files import FilesCapability
from jarvis.capabilities.interaction import InteractionCapability
from jarvis.capabilities.keyboard import KeyboardCapability
from jarvis.capabilities.media import MediaCapability
from jarvis.capabilities.messaging import MessagingCapability
from jarvis.capabilities.mouse import MouseCapability
from jarvis.capabilities.screenshot import ScreenshotCapability
from jarvis.capabilities.system import SystemCapability
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.capabilities.vision import VisionCapability
from jarvis.capabilities.windows import WindowCapability
from jarvis.live.config import get_vision_model
from jarvis.tools.vision import VisionTools


if TYPE_CHECKING:
    from jarvis.live.registry import ToolRegistry


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

    from jarvis.live.registry import ToolRegistry

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


