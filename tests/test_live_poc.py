import asyncio
import logging
import os
import pathlib
import tomllib
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from livekit.agents import AgentServer
from livekit.agents.cli.discover import ModuleData, get_app_name

from jarvis.live import agent
from jarvis.live.config import (
    DEFAULT_GEMINI_LIVE_MODEL,
    LiveConfig,
    debug_live,
    get_live_config,
    get_required_runtime_env_names,
)
from jarvis.live.logging import (
    REDACTED_PII_VALUE,
    install_livekit_pii_log_filter,
)
from jarvis.live.prompts import LIVE_SYSTEM_PROMPT
from jarvis.live.tools import ToolRegistry, create_live_tools
from jarvis.capabilities.results import ToolResult
from jarvis.security import SecurityDecision
from jarvis.voice_mode import VoiceMode


EXPECTED_LIVE_TOOL_NAMES = [
    "activate_ui_element",
    "ask_about_screen",
    "browse_activate_tab",
    "browse_get_active_tab",
    "browse_list_tabs",
    "browse_open_url",
    "browse_search_web",
    "cancel_action",
    "cancel_task",
    "capture_region",
    "capture_screen",
    "capture_window",
    "clear_clipboard",
    "click",
    "close_app",
    "confirm_action",
    "create_folder",
    "describe_screen",
    "double_click",
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
    "get_system_info",
    "get_volume",
    "hotkey",
    "inspect_ui",
    "is_app_running",
    "list_files",
    "list_memories",
    "lock_screen",
    "maximize_window",
    "minimize_window",
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
    "propose_memory",
    "recall",
    "recent_activity",
    "remember",
    "rename_file",
    "right_click",
    "run_procedure",
    "run_task",
    "save_task_procedure",
    "scroll",
    "search_the_web",
    "select_all_and_copy",
    "select_all_and_delete",
    "send_last_web_result",
    "send_prompt_to_app",
    "set_brightness",
    "set_clipboard_text",
    "set_volume",
    "task_status",
    "type_text",
]


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
        RecordingAgentSession.instances.append(self)

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


class RecordingLiveMacOSTools:
    def __init__(
        self,
        error=None,
        volume=40,
        get_error=None,
        app_running=True,
        open_error=None,
        close_error=None,
        running_error=None,
        media_state=None,
        media_error=None,
        battery=None,
        system_info=None,
        brightness=50,
        system_error=None,
        lock_state=None,
        window_state=None,
        window_error=None,
    ):
        self.error = error
        self.volume = volume
        self.get_error = get_error
        self.app_running = app_running
        self.open_error = open_error
        self.close_error = close_error
        self.running_error = running_error
        self.media_state = media_state or {
            "media_available": True,
            "playing": True,
            "title": "Song",
            "artist": "Artist",
            "app": "Music",
        }
        self.media_error = media_error
        self.battery = battery or {
            "percentage": 74,
            "charging": True,
            "charged": False,
            "external_power": True,
            "raw": "test battery",
        }
        self.system_info = system_info or {
            "model_name": "MacBook Pro",
            "model_identifier": "Mac15,3",
            "chip": "Apple M3",
            "memory": "8 GB",
            "serial_number": "TEST123",
        }
        self.brightness = brightness
        self.system_error = system_error
        self.lock_state = lock_state or {
            "command_executed": True,
            "state_confirmed": False,
            "locked": None,
            "backend": "test_backend",
        }
        self.window_state = window_state or {
            "target_app": "Safari",
            "frontmost": True,
            "window_title": "Example",
            "position": {"x": 0, "y": 25},
            "size": {"width": 800, "height": 600},
            "minimized": False,
            "fullscreen": False,
            "command_executed": True,
            "state_confirmed": True,
            "previous_position": {"x": 100, "y": 100},
            "previous_size": {"width": 600, "height": 400},
        }
        self.window_error = window_error
        self.calls = []
        self.get_calls = 0
        self.open_calls = []
        self.close_calls = []
        self.running_calls = []
        self.play_calls = 0
        self.next_calls = 0
        self.previous_calls = 0
        self.media_state_calls = 0
        self.battery_calls = 0
        self.system_info_calls = 0
        self.get_brightness_calls = 0
        self.set_brightness_calls = []
        self.lock_calls = 0
        self.active_window_calls = 0
        self.focus_window_calls = []
        self.minimize_window_calls = []
        self.maximize_window_calls = []
        self.move_window_calls = []

    def set_volume(self, level):
        self.calls.append(level)

        if self.error is not None:
            raise self.error

        return f"Volume regle a {level} %."

    def get_volume(self):
        self.get_calls += 1

        if self.get_error is not None:
            raise self.get_error

        return self.volume

    def open_app(self, app_name):
        self.open_calls.append(app_name)

        if self.open_error is not None:
            raise self.open_error

        return f"{app_name} a ete ouvert."

    def close_app(self, app_name):
        self.close_calls.append(app_name)

        if self.close_error is not None:
            raise self.close_error

        return f"{app_name} a ete ferme."

    def is_app_running(self, app_name):
        self.running_calls.append(app_name)

        if self.running_error is not None:
            raise self.running_error

        return self.app_running

    def play_pause(self):
        self.play_calls += 1

        if self.media_error is not None:
            raise self.media_error

        return dict(self.media_state)

    def next_track(self):
        self.next_calls += 1

        if self.media_error is not None:
            raise self.media_error

        return dict(self.media_state)

    def previous_track(self):
        self.previous_calls += 1

        if self.media_error is not None:
            raise self.media_error

        return dict(self.media_state)

    def get_media_state(self):
        self.media_state_calls += 1

        if self.media_error is not None:
            raise self.media_error

        return dict(self.media_state)

    def get_battery_status(self):
        self.battery_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return dict(self.battery)

    def get_system_info(self):
        self.system_info_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return dict(self.system_info)

    def get_brightness(self):
        self.get_brightness_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return self.brightness

    def set_brightness(self, level):
        self.set_brightness_calls.append(level)

        if self.system_error is not None:
            raise self.system_error

        return {
            "requested_brightness": level,
            "brightness": level,
        }

    def lock_screen(self):
        self.lock_calls += 1

        if self.system_error is not None:
            raise self.system_error

        return dict(self.lock_state)

    def get_active_window(self):
        self.active_window_calls += 1

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)

    def focus_window(self, app_name):
        self.focus_window_calls.append(app_name)

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)

    def minimize_window(self, app_name=None):
        self.minimize_window_calls.append(app_name)

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)

    def maximize_window(self, app_name=None):
        self.maximize_window_calls.append(app_name)

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)

    def move_window(self, position, app_name=None):
        self.move_window_calls.append((position, app_name))

        if self.window_error is not None:
            raise self.window_error

        return dict(self.window_state)


class RecordingLiveFileSystemTools:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def list_files(self, path=None):
        self.calls.append(("list_files", path))
        self._raise_if_needed()
        return {
            "path": "/Users/test",
            "results": [],
            "result_count": 0,
            "truncated": False,
        }

    def find_files(self, query, path=None):
        self.calls.append(("find_files", query, path))
        self._raise_if_needed()
        return {
            "query": query,
            "path": "/Users/test",
            "results": [{"path": "/Users/test/report.pdf", "name": "report.pdf"}],
            "result_count": 1,
            "truncated": False,
        }

    def get_file_info(self, path):
        self.calls.append(("get_file_info", path))
        self._raise_if_needed()
        return {
            "path": path,
            "name": "report.pdf",
            "kind": "file",
            "size_bytes": 42,
            "modified_at": "2026-09-23T12:00:00",
            "is_hidden": False,
            "is_symlink": False,
        }

    def open_file(self, path):
        self.calls.append(("open_file", path))
        self._raise_if_needed()
        return {
            "path": path,
            "command_executed": True,
            "state_confirmed": False,
        }

    def open_folder(self, path):
        self.calls.append(("open_folder", path))
        self._raise_if_needed()
        return {
            "path": path,
            "command_executed": True,
            "state_confirmed": False,
        }

    def create_folder(self, path):
        self.calls.append(("create_folder", path))
        self._raise_if_needed()
        return {
            "path": path,
            "command_executed": True,
            "state_confirmed": True,
        }

    def rename_file(self, path, new_name):
        self.calls.append(("rename_file", path, new_name))
        self._raise_if_needed()
        return {
            "previous_path": path,
            "path": f"/Users/test/{new_name}",
            "destination": f"/Users/test/{new_name}",
            "command_executed": True,
            "state_confirmed": True,
        }

    def move_file(self, source, destination):
        self.calls.append(("move_file", source, destination))
        self._raise_if_needed()
        return {
            "previous_path": source,
            "path": destination,
            "destination": destination,
            "command_executed": True,
            "state_confirmed": True,
        }


class RecordingLiveClipboardTools:
    def __init__(self, error=None, text_state=None, set_state=None, clear_state=None):
        self.error = error
        self.text_state = text_state or {
            "has_text": True,
            "text": "Bonjour",
            "length": 7,
            "returned_length": 7,
            "truncated": False,
            "content_type": "text",
        }
        self.set_state = set_state or {
            "command_executed": True,
            "state_confirmed": True,
            "length": 7,
            "has_text": True,
            "content_type": "text",
        }
        self.clear_state = clear_state or {
            "command_executed": True,
            "state_confirmed": True,
            "length": 0,
            "has_text": False,
            "content_type": "no_text_detected",
        }
        self.calls = []

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def get_text(self):
        self.calls.append(("get_text",))
        self._raise_if_needed()
        return dict(self.text_state)

    def set_text(self, text):
        self.calls.append(("set_text", text))
        self._raise_if_needed()
        return dict(self.set_state)

    def clear(self):
        self.calls.append(("clear",))
        self._raise_if_needed()
        return dict(self.clear_state)


class RecordingLiveKeyboardCapability:
    def __init__(self, error_result=None):
        self.error_result = error_result
        self.calls = []

    def type_text(self, text):
        self.calls.append(("type_text", text))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="type_text",
            message=(
                "La commande de saisie a ete envoyee, mais Jarvis ne peut "
                "pas confirmer que le texte a ete applique."
            ),
            command_executed=True,
            state_confirmed=False,
            length=len(text),
            target_app="Safari",
            target_window="Example",
        )

    def press_key(self, key):
        self.calls.append(("press_key", key))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="press_key",
            message="La touche a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            key=key,
            target_app="Safari",
            target_window="Example",
        )

    def hotkey(self, keys):
        self.calls.append(("hotkey", keys))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="hotkey",
            message="Le raccourci clavier a ete envoye.",
            command_executed=True,
            state_confirmed=False,
            keys=list(keys),
            target_app="Safari",
            target_window="Example",
        )


class RecordingLiveMouseCapability:
    def __init__(self, error_result=None):
        self.error_result = error_result
        self.calls = []

    def get_mouse_position(self):
        self.calls.append(("get_mouse_position",))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="get_mouse_position",
            message="La souris est en position x=10, y=20.",
            x=10,
            y=20,
            screen_index=0,
        )

    def move_mouse(self, x, y):
        self.calls.append(("move_mouse", x, y))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="move_mouse",
            message="Le pointeur a ete deplace.",
            command_executed=True,
            state_confirmed=True,
            previous_x=1,
            previous_y=2,
            target_x=x,
            target_y=y,
            x=x,
            y=y,
            screen_index=0,
        )

    def click(self):
        self.calls.append(("click",))
        return self._click_result("click", "left", 1)

    def double_click(self):
        self.calls.append(("double_click",))
        return self._click_result("double_click", "left", 2)

    def right_click(self):
        self.calls.append(("right_click",))
        return self._click_result("right_click", "right", 1)

    def scroll(self, direction, amount=3):
        self.calls.append(("scroll", direction, amount))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="scroll",
            message="La commande de scroll a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            direction=direction,
            amount=amount,
            x=10,
            y=20,
            screen_index=0,
        )

    def _click_result(self, action, button, click_count):
        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action=action,
            message="La commande de clic a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            button=button,
            click_count=click_count,
            x=10,
            y=20,
            screen_index=0,
        )


class RecordingLiveUIAccessibilityCapability:
    def __init__(self, error_result=None):
        self.error_result = error_result
        self.calls = []

    def inspect_ui(self, max_depth=4, max_elements=80):
        self.calls.append(("inspect_ui", max_depth, max_elements))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="inspect_ui",
            message="1 element Accessibility exploitable a ete trouve.",
            elements=[{"role": "AXButton", "title": "Continuer"}],
            count=1,
            truncated=False,
            max_depth=max_depth,
            max_elements=max_elements,
        )

    def find_ui_elements(self, query, role=None):
        self.calls.append(("find_ui_elements", query, role))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="find_ui_elements",
            message="Un element Accessibility correspond a cette recherche.",
            query_length=len(query),
            role=role,
            candidates=[{"role": role or "AXButton", "title": "Continuer"}],
            candidate_count=1,
            truncated=False,
        )

    def focus_ui_element(self, query, role=None):
        self.calls.append(("focus_ui_element", query, role))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="focus_ui_element",
            message="Le focus Accessibility a ete confirme.",
            command_executed=True,
            state_confirmed=True,
            candidate={"role": role or "AXTextField"},
            element={"role": role or "AXTextField", "focused": True},
        )

    def activate_ui_element(self, query, role=None):
        self.calls.append(("activate_ui_element", query, role))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="activate_ui_element",
            message="La commande Accessibility a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            candidate={"role": role or "AXButton"},
            element={"role": role or "AXButton"},
        )


class RecordingLiveInteractionCapability:
    def __init__(self, error_result=None):
        self.error_result = error_result
        self.calls = []

    def select_all_and_copy(self):
        self.calls.append(("select_all_and_copy",))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="select_all_and_copy",
            message="Les commandes ont ete envoyees dans l'ordre.",
            command_executed=True,
            state_confirmed=False,
            steps=[
                {"name": "hotkey_command_a", "ok": True},
                {"name": "hotkey_command_c", "ok": True},
            ],
        )

    def focus_app_ui_and_type(
        self,
        app_name,
        text,
        query=None,
        role=None,
        press_enter=False,
    ):
        self.calls.append((
            "focus_app_ui_and_type",
            app_name,
            text,
            query,
            role,
            press_enter,
        ))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="focus_app_ui_and_type",
            message="La cible a ete verifiee et la saisie envoyee.",
            command_executed=True,
            state_confirmed=False,
            target_app=app_name,
            query_length=len(query) if isinstance(query, str) else None,
            text_length=len(text) if isinstance(text, str) else None,
            role=role,
            press_enter=press_enter,
            steps=[
                {"name": "open_app", "ok": True},
                {"name": "focus_window", "ok": True, "state_confirmed": True},
                {"name": "type_text", "ok": True, "command_executed": True},
            ],
        )

    def select_all_and_delete(self):
        self.calls.append(("select_all_and_delete",))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="select_all_and_delete",
            message="La cible a ete verifiee et la suppression a ete envoyee.",
            command_executed=True,
            state_confirmed=False,
            deletion_executed=True,
            steps=[
                {"name": "inspect_editable_target", "ok": True},
                {"name": "hotkey_command_a", "ok": True},
                {"name": "delete_selection", "ok": True},
            ],
        )

    def open_app_and_type(self, app_name, text, press_enter=True):
        self.calls.append(("open_app_and_type", app_name, text, press_enter))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="open_app_and_type",
            message="Saisie directe envoyee.",
            command_executed=True,
            state_confirmed=False,
            target_app=app_name,
            text_length=len(text) if isinstance(text, str) else None,
            press_enter=press_enter,
            steps=[
                {"name": "open_app", "ok": True},
                {"name": "type_text", "ok": True, "command_executed": True},
            ],
        )

    def open_app_and_focus_ui(self, app_name, query, role=None):
        self.calls.append(("open_app_and_focus_ui", app_name, query, role))

        if self.error_result is not None:
            return self.error_result

        return ToolResult.success(
            action="open_app_and_focus_ui",
            message="La cible Accessibility a ete focalisee.",
            command_executed=True,
            state_confirmed=True,
            target_app=app_name,
            query_length=len(query),
            role=role,
            steps=[
                {"name": "open_app", "ok": True},
                {"name": "focus_window", "ok": True, "state_confirmed": True},
                {"name": "focus_ui_element", "ok": True, "state_confirmed": True},
            ],
        )


class LivePocConfigTest(unittest.TestCase):
    def test_pyproject_marks_repository_as_agent_project_for_livekit_cli(self):
        pyproject_path = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"

        self.assertTrue(pyproject_path.exists())

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["name"], "jarvis")
        self.assertEqual(data["project"]["requires-python"], ">=3.13")

    def test_default_live_model_is_centralized(self):
        with patch.dict(os.environ, {}, clear=True):
            config = get_live_config()

        self.assertEqual(config.model, DEFAULT_GEMINI_LIVE_MODEL)
        self.assertEqual(config.voice, "Puck")
        self.assertEqual(config.agent_name, "jarvis-live-poc")

    def test_live_model_can_be_overridden(self):
        with patch.dict(
            os.environ,
            {
                "JARVIS_GEMINI_LIVE_MODEL": "gemini-test-live",
                "JARVIS_GEMINI_LIVE_VOICE": "Aoede",
                "JARVIS_GEMINI_LIVE_TEMPERATURE": "0.4",
                "JARVIS_LIVE_AGENT_NAME": "jarvis-test",
            },
            clear=True,
        ):
            config = get_live_config()

        self.assertEqual(config.model, "gemini-test-live")
        self.assertEqual(config.voice, "Aoede")
        self.assertEqual(config.temperature, 0.4)
        self.assertEqual(config.agent_name, "jarvis-test")

    def test_required_runtime_env_names_are_documented_by_code(self):
        self.assertEqual(
            get_required_runtime_env_names(),
            (
                "GOOGLE_API_KEY",
                "LIVEKIT_URL",
                "LIVEKIT_API_KEY",
                "LIVEKIT_API_SECRET",
            ),
        )

    def test_debug_live_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                debug_live("event", model="gemini")

        self.assertEqual(output.getvalue(), "")

    def test_debug_live_outputs_non_secret_fields_when_enabled(self):
        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                debug_live("event", model="gemini")

        debug_output = output.getvalue()

        self.assertIn("JARVIS LIVE DEBUG", debug_output)
        self.assertIn("EVENT: event", debug_output)
        self.assertIn("model: gemini", debug_output)


class LiveLoggingPrivacyTest(unittest.TestCase):
    def emit_livekit_log(self, **extra):
        logger = logging.getLogger("livekit.agents")
        old_level = logger.level
        old_propagate = logger.propagate
        records = []

        class RecordingHandler(logging.Handler):
            def emit(self, record):
                records.append(dict(record.__dict__))

        handler = RecordingHandler()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        try:
            install_livekit_pii_log_filter()
            logger.debug("executing tool", extra=extra)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
            logger.propagate = old_propagate

        self.assertEqual(len(records), 1)
        return records[0]

    def test_livekit_pii_arguments_are_redacted_in_local_logs(self):
        secret = "JARVIS_SECRET_ARGUMENT_SENTINEL_2ef6"

        record = self.emit_livekit_log(
            function="set_clipboard_text",
            **{"lk.pii.arguments": f'{{"text": "{secret}"}}'},
        )

        self.assertEqual(record["function"], "set_clipboard_text")
        self.assertEqual(record["lk.pii.arguments"], REDACTED_PII_VALUE)
        self.assertNotIn(secret, str(record))

    def test_livekit_pii_text_is_redacted_in_local_logs(self):
        secret = "JARVIS_SECRET_TEXT_SENTINEL_9b03"

        record = self.emit_livekit_log(
            role="user",
            **{"lk.pii.text": secret},
        )

        self.assertEqual(record["role"], "user")
        self.assertEqual(record["lk.pii.text"], REDACTED_PII_VALUE)
        self.assertNotIn(secret, str(record))

    def test_livekit_nested_pii_fields_are_redacted_in_local_logs(self):
        secret = "JARVIS_SECRET_OUTPUT_SENTINEL_b75c"

        record = self.emit_livekit_log(
            function="get_clipboard_text",
            **{"lk.pii.function_tool.output": f'{{"text": "{secret}"}}'},
        )

        self.assertEqual(
            record["lk.pii.function_tool.output"],
            REDACTED_PII_VALUE,
        )
        self.assertNotIn(secret, str(record))

    def test_livekit_non_pii_log_fields_are_unchanged(self):
        record = self.emit_livekit_log(
            function="get_volume",
            safe_field="visible diagnostic",
        )

        self.assertEqual(record["function"], "get_volume")
        self.assertEqual(record["safe_field"], "visible diagnostic")

    def test_livekit_pii_filter_installation_is_idempotent(self):
        logger = logging.getLogger("livekit.agents")

        install_livekit_pii_log_filter()
        install_livekit_pii_log_filter()

        filters = [
            item
            for item in logger.filters
            if item.__class__.__name__ == "LiveKitPIILogFilter"
        ]
        self.assertEqual(len(filters), 1)


class LivePocAgentTest(unittest.TestCase):
    def test_realtime_model_is_created_from_config(self):
        fake_google = FakeGoogle()
        config = LiveConfig(
            model="gemini-test-live",
            voice="Aoede",
            temperature=0.5,
            agent_name="jarvis-test",
        )

        model = agent.create_realtime_model(fake_google, config)

        self.assertEqual(model["type"], "realtime-model")
        self.assertEqual(
            fake_google.realtime.created,
            [
                {
                    "model": "gemini-test-live",
                    "voice": "Aoede",
                    "temperature": 0.5,
                    "instructions": LIVE_SYSTEM_PROMPT,
                }
            ],
        )

    def test_assistant_class_uses_minimal_live_prompt(self):
        assistant_class = agent.create_assistant_class(FakeAgentBase)

        assistant = assistant_class()

        self.assertEqual(assistant.kwargs["instructions"], LIVE_SYSTEM_PROMPT)
        self.assertEqual(
            sorted(tool.info.name for tool in assistant.kwargs["tools"]),
            EXPECTED_LIVE_TOOL_NAMES,
        )

    def test_live_prompt_requires_fresh_state_tools_for_current_state(self):
        self.assertIn("état actuel du Mac", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_media_state pour le média", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_volume pour le volume", LIVE_SYSTEM_PROMPT)
        self.assertIn("is_app_running pour une application", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_battery_status pour la batterie", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_brightness pour la luminosité", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_system_info pour les informations du Mac", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_active_window pour la fenêtre active", LIVE_SYSTEM_PROMPT)
        self.assertIn("appelle uniquement le tool d'action média", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne lance pas get_media_state en parallèle", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour changer la luminosité", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour verrouiller le Mac", LIVE_SYSTEM_PROMPT)
        self.assertIn("state_confirmed=false", LIVE_SYSTEM_PROMPT)
        self.assertIn("locked=null", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne dis jamais que le Mac est verrouillé", LIVE_SYSTEM_PROMPT)
        self.assertIn("la commande a été envoyée", LIVE_SYSTEM_PROMPT)
        self.assertIn("n'a pas pu être confirmé", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour contrôler les fenêtres", LIVE_SYSTEM_PROMPT)
        self.assertIn("maximize_window agrandit la fenêtre sans plein écran", LIVE_SYSTEM_PROMPT)
        self.assertIn("move_window avec position=fullscreen", LIVE_SYSTEM_PROMPT)
        self.assertIn("tool de fenêtre retourne state_confirmed=false", LIVE_SYSTEM_PROMPT)
        self.assertIn('Ne dis jamais "je vois"', LIVE_SYSTEM_PROMPT)
        self.assertIn("je confirme visuellement", LIVE_SYSTEM_PROMPT)
        self.assertIn("d'après l'état de la fenêtre", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour les fichiers et dossiers", LIVE_SYSTEM_PROMPT)
        self.assertIn("état actuel du filesystem", LIVE_SYSTEM_PROMPT)
        self.assertIn("chemins absolus retournes par les tools Files", LIVE_SYSTEM_PROMPT)
        self.assertIn("ambiguous_path", LIVE_SYSTEM_PROMPT)
        self.assertIn("contenu ACTUEL du presse-papiers", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_clipboard_text", LIVE_SYSTEM_PROMPT)
        self.assertIn("set_clipboard_text", LIVE_SYSTEM_PROMPT)
        self.assertIn("clear_clipboard", LIVE_SYSTEM_PROMPT)
        self.assertIn("truncated=true", LIVE_SYSTEM_PROMPT)
        self.assertIn("content_type=no_text_detected", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne reponds jamais depuis l'historique", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour les actions clavier", LIVE_SYSTEM_PROMPT)
        self.assertIn("fenetre actuellement active", LIVE_SYSTEM_PROMPT)
        self.assertIn("focus_window d'abord et attends son resultat", LIVE_SYSTEM_PROMPT)
        self.assertIn("type_text n'appuie jamais automatiquement sur Entree", LIVE_SYSTEM_PROMPT)
        self.assertIn("state_confirmed=false", LIVE_SYSTEM_PROMPT)
        self.assertIn("command_executed=true signifie uniquement", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne dis jamais que l'effet dans l'application s'est produit", LIVE_SYSTEM_PROMPT)
        self.assertIn("c'est copie", LIVE_SYSTEM_PROMPT)
        self.assertIn("j'ai annule", LIVE_SYSTEM_PROMPT)
        self.assertIn("cela a fonctionne", LIVE_SYSTEM_PROMPT)
        self.assertIn("normalement", LIVE_SYSTEM_PROMPT)
        self.assertIn("probablement", LIVE_SYSTEM_PROMPT)
        self.assertIn("ca devrait etre bon", LIVE_SYSTEM_PROMPT)
        self.assertIn("la commande clavier a ete envoyee", LIVE_SYSTEM_PROMPT)
        self.assertIn("texte sensible inutilement", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour la souris", LIVE_SYSTEM_PROMPT)
        self.assertIn("get_mouse_position", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne deduis jamais cette position depuis l'historique", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne devine jamais de coordonnees", LIVE_SYSTEM_PROMPT)
        self.assertIn("MouseCapability ne comprend pas l'interface", LIVE_SYSTEM_PROMPT)
        self.assertIn("attends son resultat", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne lance jamais move_mouse et click en parallele", LIVE_SYSTEM_PROMPT)
        self.assertIn("command_executed=true autorise seulement", LIVE_SYSTEM_PROMPT)
        self.assertIn("executee cote systeme", LIVE_SYSTEM_PROMPT)
        self.assertIn("l'effet applicatif est confirme", LIVE_SYSTEM_PROMPT)
        self.assertIn("c'est fait", LIVE_SYSTEM_PROMPT)
        self.assertIn("le defilement a reussi", LIVE_SYSTEM_PROMPT)
        self.assertIn("le clic a fonctionne", LIVE_SYSTEM_PROMPT)
        self.assertIn("le bouton a ete active", LIVE_SYSTEM_PROMPT)
        self.assertIn("D'accord.", LIVE_SYSTEM_PROMPT)
        self.assertIn("Je l'ai envoye.", LIVE_SYSTEM_PROMPT)
        self.assertIn("Voila.", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne demande pas systematiquement", LIVE_SYSTEM_PROMPT)
        self.assertIn("est-ce que ca a fonctionne", LIVE_SYSTEM_PROMPT)
        self.assertIn("est-ce que ca te convient", LIVE_SYSTEM_PROMPT)
        self.assertIn("qu'est-ce que tu vois", LIVE_SYSTEM_PROMPT)
        self.assertIn("necessaire pour poursuivre une sequence dependante", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pas de spam de clics", LIVE_SYSTEM_PROMPT)
        self.assertIn("pas de drag/drop en V1", LIVE_SYSTEM_PROMPT)
        self.assertIn("Pour comprendre l'interface macOS", LIVE_SYSTEM_PROMPT)
        self.assertIn("inspect_ui", LIVE_SYSTEM_PROMPT)
        self.assertIn("find_ui_elements", LIVE_SYSTEM_PROMPT)
        self.assertIn("activate_ui_element", LIVE_SYSTEM_PROMPT)
        self.assertIn("preferes a MouseCapability", LIVE_SYSTEM_PROMPT)
        self.assertIn("ne dis jamais \"je vois\"", LIVE_SYSTEM_PROMPT)
        self.assertIn("\"je vois que\"", LIVE_SYSTEM_PROMPT)
        self.assertIn("d'apres l'interface accessible", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne reutilise jamais un ancien resultat Accessibility", LIVE_SYSTEM_PROMPT)
        self.assertIn("Si plusieurs elements correspondent", LIVE_SYSTEM_PROMPT)
        self.assertIn("N'invente jamais un bouton absent", LIVE_SYSTEM_PROMPT)
        self.assertIn("AXPress reussi signifie seulement", LIVE_SYSTEM_PROMPT)
        self.assertIn("Ne repete jamais automatiquement AXPress", LIVE_SYSTEM_PROMPT)

    def test_live_prompt_defines_multi_step_orchestration_rules(self):
        prompt = LIVE_SYSTEM_PROMPT

        self.assertIn("fournis obligatoirement query", prompt)
        self.assertIn('query="recherche"', prompt)
        self.assertIn('query="Nom"', prompt)
        self.assertIn("editable_target_not_verified", prompt)
        self.assertIn("sans contourner le controle par type_text directement", prompt)

        self.assertIn("demandes naturelles multi-etapes", prompt)
        self.assertIn("strictement sequentielle", prompt)
        self.assertIn("Attends toujours le resultat d'une etape", prompt)
        self.assertIn("utilise select_all_and_copy", prompt)
        self.assertIn("au lieu de lancer separement les hotkeys", prompt)
        self.assertIn("utilise focus_app_ui_and_type", prompt)
        self.assertIn("utilise open_app_and_focus_ui", prompt)

        dependent_sequences = [
            "open_app -> focus_window/get_active_window",
            "focus_window -> inspect_ui/find_ui_elements",
            "focus_ui_element -> type_text",
            "move_mouse -> click",
            "hotkey command+a -> hotkey command+c",
        ]

        for sequence in dependent_sequences:
            with self.subTest(sequence=sequence):
                self.assertIn(sequence, prompt)

        self.assertIn("operations dependantes cross-capability", prompt)
        self.assertIn("Si une etape retourne ok=false", prompt)
        self.assertIn("arrete toutes les etapes qui dependent", prompt)
        self.assertIn("ne substitue pas automatiquement une autre methode", prompt)
        self.assertIn("state_confirmed=false et que l'etape suivante depend", prompt)
        self.assertIn("n'annonce pas de succes applicatif", prompt)
        self.assertIn("n'interdit pas toute action suivante", prompt)
        self.assertIn("Apres open_app, ne suppose pas", prompt)
        self.assertIn("les anciens resultats inspect_ui et find_ui_elements sont obsoletes", prompt)
        self.assertIn("Avant type_text", prompt)
        self.assertIn("verifie ou focalise la bonne cible", prompt)
        self.assertIn("fenetre simplement supposee active", prompt)
        self.assertIn("Pour une cible semantique", prompt)
        self.assertIn("prefere Accessibility", prompt)
        self.assertIn("n'ajoute aucun fallback souris automatique", prompt)
        self.assertIn("ambiguous_ui_element", prompt)
        self.assertIn("ne choisis jamais silencieusement", prompt)
        self.assertIn("Apres une reconnexion", prompt)
        self.assertIn("ne repete jamais automatiquement une mutation", prompt)
        self.assertIn("command_executed=false", prompt)
        self.assertIn("ancien tool call ne prouve pas l'etat actuel", prompt)
        self.assertIn("Ces regles sont internes", prompt)
        self.assertIn("reponds naturellement", prompt)
        self.assertIn("parametres techniques", prompt)

    def test_live_agent_exposes_module_level_server_for_livekit_cli(self):
        self.assertTrue(hasattr(agent, "build_live_server"))
        self.assertTrue(hasattr(agent, "server"))
        self.assertIsInstance(agent.server, AgentServer)

    def test_livekit_cli_discovery_finds_server_variable(self):
        app_name = get_app_name(
            mod_data=ModuleData(
                module_import_str="jarvis.live.agent",
                extra_sys_path=pathlib.Path("src"),
                module_paths=[],
            )
        )

        self.assertEqual(app_name, "server")

    def test_imported_server_is_not_started_before_cli_runs_it(self):
        self.assertFalse(hasattr(agent.server, "_proc_pool"))

    def test_realtime_model_creation_is_deferred_until_session_job(self):
        config = LiveConfig(
            model="gemini-test-live",
            voice="Puck",
            temperature=0.8,
            agent_name="jarvis-test",
        )

        with patch.object(
            agent,
            "create_realtime_model",
            side_effect=AssertionError("Realtime model should be deferred"),
        ):
            built_server = agent.build_live_server(config)

        self.assertIsInstance(built_server, AgentServer)
        self.assertFalse(hasattr(built_server, "_proc_pool"))

    def test_live_session_start_enables_livekit_recording_redaction(self):
        config = LiveConfig(
            model="gemini-test-live",
            voice="Puck",
            temperature=0.8,
            agent_name="jarvis-test",
        )
        RecordingAgentSession.instances.clear()

        with patch("livekit.agents.AgentSession", RecordingAgentSession):
            with patch.object(
                agent,
                "create_realtime_model",
                return_value={"type": "fake-model"},
            ):
                built_server = agent.build_live_server(config)
                asyncio.run(built_server._entrypoint_fnc(FakeJobContext()))

        session = RecordingAgentSession.instances[0]
        self.assertEqual(
            session.start_calls[0]["record"],
            {"redaction": True},
        )
        self.assertIs(session.start_calls[0]["room"], FakeJobContext.room)

    def test_voice_mode_still_imports_alongside_live_poc(self):
        self.assertTrue(hasattr(VoiceMode, "run"))

    def test_no_secret_values_are_hardcoded_in_live_modules(self):
        live_source = (
            agent.__loader__.get_source(agent.__name__)
            + "\n"
            + debug_live.__globals__["__loader__"].get_source(
                debug_live.__module__
            )
        )

        forbidden_fragments = (
            "AIza",
            "LIVEKIT_API_SECRET=",
            "GOOGLE_API_KEY=",
        )

        for fragment in forbidden_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, live_source)

    def test_tool_registry_exposes_audio_and_app_tools(self):
        registry = ToolRegistry(
            audio_capability=object(),
            app_capability=object(),
        )

        tools = registry.livekit_tools()

        self.assertEqual(
            sorted(tool.info.name for tool in tools),
            EXPECTED_LIVE_TOOL_NAMES,
        )


class LiveSetVolumeToolTest(unittest.TestCase):
    def make_tools(self, security=None, macos_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            macos_tools=macos_tools or RecordingLiveMacOSTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def make_tool(self, security=None, macos_tools=None):
        return self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["set_volume"]

    def test_set_volume_success_uses_security_then_macos_tools(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tool(security=security, macos_tools=macos_tools)

        result = asyncio.run(tool(40))

        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "set_volume")
        self.assertEqual(security.intents[0].target, "40")
        self.assertEqual(macos_tools.calls, [40])
        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "set_volume",
                "volume": 40,
                "message": "Volume regle a 40 %.",
            },
        )

    def test_set_volume_accepts_lower_boundary(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tool(macos_tools=macos_tools)

        result = asyncio.run(tool(0))

        self.assertTrue(result["ok"])
        self.assertEqual(result["volume"], 0)
        self.assertEqual(macos_tools.calls, [0])

    def test_set_volume_accepts_upper_boundary(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tool(macos_tools=macos_tools)

        result = asyncio.run(tool(100))

        self.assertTrue(result["ok"])
        self.assertEqual(result["volume"], 100)
        self.assertEqual(macos_tools.calls, [100])

    def test_set_volume_rejects_negative_value_before_macos_tools(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tool(security=security, macos_tools=macos_tools)

        result = asyncio.run(tool(-1))

        self.assertFalse(result["ok"])
        self.assertIn("0 et 100", result["message"])
        self.assertEqual(security.intents, [])
        self.assertEqual(macos_tools.calls, [])

    def test_set_volume_rejects_value_over_100_before_macos_tools(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tool(security=security, macos_tools=macos_tools)

        result = asyncio.run(tool(101))

        self.assertFalse(result["ok"])
        self.assertIn("0 et 100", result["message"])
        self.assertEqual(security.intents, [])
        self.assertEqual(macos_tools.calls, [])

    def test_set_volume_security_refusal_does_not_call_macos_tools(self):
        security = RecordingLiveSecurity(allowed=False)
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tool(security=security, macos_tools=macos_tools)

        result = asyncio.run(tool(40))

        self.assertFalse(result["ok"])
        self.assertIn("pas autorise", result["message"])
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(macos_tools.calls, [])

    def test_set_volume_macos_failure_returns_explicit_failure(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools(error=RuntimeError("osascript failed"))
        tool = self.make_tool(security=security, macos_tools=macos_tools)

        result = asyncio.run(tool(40))

        self.assertFalse(result["ok"])
        self.assertIn("Echec", result["message"])
        self.assertIn("osascript failed", result["message"])
        self.assertEqual(macos_tools.calls, [40])

    def test_live_tool_is_named_set_volume_for_gemini(self):
        tool = self.make_tool()

        self.assertEqual(tool.info.name, "set_volume")
        self.assertIn("volume", tool.info.description.lower())

    def test_set_volume_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tool()

        result = tool(40)

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])


class LiveGetVolumeToolTest(unittest.TestCase):
    def make_tool(self, macos_tools=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            macos_tools=macos_tools or RecordingLiveMacOSTools(),
        )
        by_name = {
            tool.info.name: tool
            for tool in tools
        }
        return by_name["get_volume"]

    def test_get_volume_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools(volume=40)
        tool = self.make_tool(macos_tools=macos_tools)

        result = asyncio.run(tool())

        self.assertEqual(macos_tools.get_calls, 1)
        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "get_volume",
                "volume": 40,
                "message": "Le volume actuel est de 40 %.",
            },
        )

    def test_get_volume_failure_returns_explicit_failure_without_value(self):
        macos_tools = RecordingLiveMacOSTools(
            get_error=RuntimeError("osascript failed"),
        )
        tool = self.make_tool(macos_tools=macos_tools)

        result = asyncio.run(tool())

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "get_volume")
        self.assertIn("Echec", result["message"])
        self.assertIn("osascript failed", result["message"])
        self.assertNotIn("volume", result)

    def test_get_volume_tool_is_named_for_gemini(self):
        tool = self.make_tool()

        self.assertEqual(tool.info.name, "get_volume")
        self.assertIn("volume", tool.info.description.lower())
        self.assertIn("actuel", tool.info.description.lower())

    def test_get_volume_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tool()

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])


class LiveAppToolTest(unittest.TestCase):
    def make_tools(self, security=None, macos_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            macos_tools=macos_tools or RecordingLiveMacOSTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_open_app_success_returns_structured_result(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["open_app"]

        result = asyncio.run(tool("Safari"))

        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "open_app")
        self.assertEqual(security.intents[0].target, "Safari")
        self.assertEqual(macos_tools.open_calls, ["Safari"])
        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "open_app",
                "target": "Safari",
                "message": "Safari a ete ouvert.",
            },
        )

    def test_close_app_success_returns_structured_result(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["close_app"]

        result = asyncio.run(tool("Spotify"))

        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "close_app")
        self.assertEqual(security.intents[0].target, "Spotify")
        self.assertEqual(macos_tools.close_calls, ["Spotify"])
        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "close_app",
                "target": "Spotify",
                "message": "Spotify a ete ferme.",
            },
        )

    def test_is_app_running_true_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools(app_running=True)
        tool = self.make_tools(macos_tools=macos_tools)["is_app_running"]

        result = asyncio.run(tool("Safari"))

        self.assertEqual(macos_tools.running_calls, ["Safari"])
        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "is_app_running",
                "target": "Safari",
                "running": True,
                "message": "Safari est actuellement ouvert.",
            },
        )

    def test_is_app_running_false_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools(app_running=False)
        tool = self.make_tools(macos_tools=macos_tools)["is_app_running"]

        result = asyncio.run(tool("Spotify"))

        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "is_app_running",
                "target": "Spotify",
                "running": False,
                "message": "Spotify n'est pas ouvert actuellement.",
            },
        )

    def test_open_app_security_refusal_does_not_call_macos_tools(self):
        security = RecordingLiveSecurity(allowed=False)
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["open_app"]

        result = asyncio.run(tool("Safari"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "open_app")
        self.assertIn("pas autorise", result["message"])
        self.assertEqual(macos_tools.open_calls, [])

    def test_open_app_macos_failure_returns_explicit_failure(self):
        macos_tools = RecordingLiveMacOSTools(
            open_error=RuntimeError("open failed"),
        )
        tool = self.make_tools(macos_tools=macos_tools)["open_app"]

        result = asyncio.run(tool("Safari"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "open_app")
        self.assertIn("open failed", result["message"])
        self.assertEqual(macos_tools.open_calls, ["Safari"])

    def test_app_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["open_app"].info.name, "open_app")
        self.assertIn("application", tools["open_app"].info.description.lower())
        self.assertEqual(tools["close_app"].info.name, "close_app")
        self.assertIn("ferme", tools["close_app"].info.description.lower())
        self.assertEqual(tools["is_app_running"].info.name, "is_app_running")
        self.assertIn("ouverte", tools["is_app_running"].info.description.lower())

    def test_app_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["open_app"]

        result = tool("Safari")

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_app_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["open_app"]
            result = asyncio.run(tool("Safari"))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("open_app", ("Safari",))])

    def test_audio_tools_remain_exposed(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("set_volume", tools)


class LiveMediaToolTest(unittest.TestCase):
    def make_tools(self, security=None, macos_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            macos_tools=macos_tools or RecordingLiveMacOSTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_play_pause_success_returns_structured_result(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["play_pause"]

        result = asyncio.run(tool())

        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "play_pause")
        self.assertEqual(macos_tools.play_calls, 1)
        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "play_pause",
                "media_available": True,
                "playing": True,
                "title": "Song",
                "artist": "Artist",
                "app": "Music",
                "message": "Song de Artist est en cours de lecture dans Music.",
            },
        )

    def test_next_track_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["next_track"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "next_track")
        self.assertEqual(result["title"], "Song")
        self.assertEqual(macos_tools.next_calls, 1)

    def test_media_command_attempts_are_serialized_for_gemini(self):
        macos_tools = RecordingLiveMacOSTools(
            media_state={
                "media_available": True,
                "playing": True,
                "title": "Previous Song",
                "artist": "Artist",
                "app": "Music",
                "command_executed": True,
                "media_observed": True,
                "previous_title": "Current Song",
                "previous_artist": "Artist",
                "track_changed": True,
                "observation_attempts": 1,
                "command_attempts": 2,
            }
        )
        tool = self.make_tools(macos_tools=macos_tools)["previous_track"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "previous_track")
        self.assertEqual(result["title"], "Previous Song")
        self.assertEqual(result["command_attempts"], 2)
        self.assertEqual(result["observation_attempts"], 1)

    def test_previous_track_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["previous_track"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "previous_track")
        self.assertEqual(result["title"], "Song")
        self.assertEqual(macos_tools.previous_calls, 1)

    def test_get_media_state_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["get_media_state"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "get_media_state")
        self.assertEqual(result["playing"], True)
        self.assertEqual(result["title"], "Song")
        self.assertEqual(macos_tools.media_state_calls, 1)

    def test_get_media_state_without_compatible_media_is_explicit(self):
        macos_tools = RecordingLiveMacOSTools(
            media_state={
                "media_available": False,
                "playing": False,
                "title": None,
                "artist": None,
                "app": None,
            }
        )
        tool = self.make_tools(macos_tools=macos_tools)["get_media_state"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertFalse(result["media_available"])
        self.assertIsNone(result["title"])
        self.assertIn("Aucun media compatible", result["message"])

    def test_media_tool_failure_returns_explicit_failure(self):
        macos_tools = RecordingLiveMacOSTools(
            media_error=RuntimeError("media failed"),
        )
        tool = self.make_tools(macos_tools=macos_tools)["play_pause"]

        result = asyncio.run(tool())

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "play_pause")
        self.assertIn("media failed", result["message"])

    def test_media_security_refusal_does_not_call_macos(self):
        security = RecordingLiveSecurity(allowed=False)
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["next_track"]

        result = asyncio.run(tool())

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "next_track")
        self.assertEqual(macos_tools.next_calls, 0)

    def test_media_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["play_pause"].info.name, "play_pause")
        self.assertIn("pause", tools["play_pause"].info.description.lower())
        self.assertEqual(tools["next_track"].info.name, "next_track")
        self.assertIn("suivant", tools["next_track"].info.description.lower())
        self.assertEqual(tools["previous_track"].info.name, "previous_track")
        self.assertIn(
            "précédent",
            tools["previous_track"].info.description.lower(),
        )
        self.assertEqual(tools["get_media_state"].info.name, "get_media_state")
        self.assertIn("morceau", tools["get_media_state"].info.description.lower())

    def test_media_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["play_pause"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_media_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["next_track"]
            result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("next_track", ())])

    def test_media_tools_share_lock_for_concurrent_livekit_calls(self):
        order = []

        async def fake_to_thread(func, *args):
            order.append(f"start:{func.__name__}")
            await asyncio.sleep(0)
            order.append(f"end:{func.__name__}")
            return func(*args)

        async def run_tools():
            tools = self.make_tools()

            with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
                return await asyncio.gather(
                    tools["next_track"](),
                    tools["get_media_state"](),
                )

        results = asyncio.run(run_tools())

        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual(order[0], "start:next_track")
        self.assertEqual(order[1], "end:next_track")
        self.assertEqual(order[2], "start:get_media_state")
        self.assertEqual(order[3], "end:get_media_state")

    def test_audio_and_app_tools_remain_exposed(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("set_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("close_app", tools)
        self.assertIn("is_app_running", tools)


class LiveSystemToolTest(unittest.TestCase):
    def make_tools(self, security=None, macos_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            macos_tools=macos_tools or RecordingLiveMacOSTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_get_battery_status_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["get_battery_status"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "get_battery_status")
        self.assertEqual(result["percentage"], 74)
        self.assertTrue(result["charging"])
        self.assertEqual(macos_tools.battery_calls, 1)

    def test_get_system_info_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["get_system_info"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["model_name"], "MacBook Pro")
        self.assertEqual(result["chip"], "Apple M3")
        self.assertEqual(macos_tools.system_info_calls, 1)

    def test_get_brightness_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools(brightness=42)
        tool = self.make_tools(macos_tools=macos_tools)["get_brightness"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["brightness"], 42)
        self.assertEqual(macos_tools.get_brightness_calls, 1)

    def test_set_brightness_success_uses_security_and_backend(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["set_brightness"]

        result = asyncio.run(tool(30))

        self.assertTrue(result["ok"])
        self.assertEqual(result["requested_brightness"], 30)
        self.assertEqual(result["brightness"], 30)
        self.assertEqual(security.intents[0].action, "set_brightness")
        self.assertEqual(macos_tools.set_brightness_calls, [30])

    def test_lock_screen_success_uses_security_and_backend(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["lock_screen"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertIsNone(result["locked"])
        self.assertEqual(security.intents[0].action, "lock_screen")
        self.assertEqual(macos_tools.lock_calls, 1)

    def test_system_tool_failure_returns_explicit_failure(self):
        macos_tools = RecordingLiveMacOSTools(
            system_error=RuntimeError("system failed"),
        )
        tool = self.make_tools(macos_tools=macos_tools)["get_battery_status"]

        result = asyncio.run(tool())

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "get_battery_status")
        self.assertIn("system failed", result["message"])

    def test_system_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["get_battery_status"].info.name, "get_battery_status")
        self.assertIn("batterie", tools["get_battery_status"].info.description.lower())
        self.assertEqual(tools["get_system_info"].info.name, "get_system_info")
        self.assertIn("modele", tools["get_system_info"].info.description.lower())
        self.assertEqual(tools["get_brightness"].info.name, "get_brightness")
        self.assertIn("luminosite", tools["get_brightness"].info.description.lower())
        self.assertEqual(tools["set_brightness"].info.name, "set_brightness")
        self.assertIn("0 et 100", tools["set_brightness"].info.description.lower())
        self.assertEqual(tools["lock_screen"].info.name, "lock_screen")
        self.assertIn("verrouille", tools["lock_screen"].info.description.lower())

    def test_system_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["get_battery_status"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_system_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["set_brightness"]
            result = asyncio.run(tool(30))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("set_brightness", (30,))])

    def test_audio_app_and_media_tools_remain_exposed(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("set_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("close_app", tools)
        self.assertIn("play_pause", tools)
        self.assertIn("get_media_state", tools)


class LiveWindowToolTest(unittest.TestCase):
    def make_tools(self, security=None, macos_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            macos_tools=macos_tools or RecordingLiveMacOSTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_get_active_window_success_returns_structured_result(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["get_active_window"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "get_active_window")
        self.assertEqual(result["target_app"], "Safari")
        self.assertEqual(result["window_title"], "Example")
        self.assertEqual(macos_tools.active_window_calls, 1)

    def test_focus_window_success_uses_security_and_backend(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["focus_window"]

        result = asyncio.run(tool("Safari"))

        self.assertTrue(result["ok"])
        self.assertEqual(security.intents[0].action, "focus_window")
        self.assertEqual(macos_tools.focus_window_calls, ["Safari"])

    def test_minimize_window_can_target_active_window(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["minimize_window"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(security.intents[0].action, "minimize_window")
        self.assertEqual(macos_tools.minimize_window_calls, [None])

    def test_maximize_window_uses_backend_without_fullscreen_claim(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["maximize_window"]

        result = asyncio.run(tool("Visual Studio Code"))

        self.assertTrue(result["ok"])
        self.assertEqual(macos_tools.maximize_window_calls, ["Visual Studio Code"])

    def test_move_window_success_passes_position_and_app_name(self):
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(macos_tools=macos_tools)["move_window"]

        result = asyncio.run(tool("left", "Safari"))

        self.assertTrue(result["ok"])
        self.assertEqual(macos_tools.move_window_calls, [("left", "Safari")])

    def test_move_window_invalid_position_is_rejected_before_backend(self):
        security = RecordingLiveSecurity()
        macos_tools = RecordingLiveMacOSTools()
        tool = self.make_tools(
            security=security,
            macos_tools=macos_tools,
        )["move_window"]

        result = asyncio.run(tool("top", "Safari"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "La position doit etre left, right, center ou fullscreen.")
        self.assertEqual(security.intents, [])
        self.assertEqual(macos_tools.move_window_calls, [])

    def test_window_tool_failure_returns_explicit_failure(self):
        macos_tools = RecordingLiveMacOSTools(
            window_error=RuntimeError("System Events erreur -10827"),
        )
        tool = self.make_tools(macos_tools=macos_tools)["get_active_window"]

        result = asyncio.run(tool())

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "get_active_window")
        self.assertIn("-10827", result["message"])

    def test_state_confirmed_false_survives_to_livekit_dict(self):
        macos_tools = RecordingLiveMacOSTools(
            window_state={
                "target_app": "Safari",
                "frontmost": True,
                "window_title": "Example",
                "position": {"x": 100, "y": 100},
                "size": {"width": 600, "height": 400},
                "minimized": False,
                "fullscreen": False,
                "command_executed": True,
                "state_confirmed": False,
                "previous_position": {"x": 100, "y": 100},
                "previous_size": {"width": 600, "height": 400},
            }
        )
        tool = self.make_tools(macos_tools=macos_tools)["move_window"]

        result = asyncio.run(tool("left", "Safari"))

        self.assertTrue(result["ok"])
        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertIn("pas pu confirmer", result["message"])

    def test_window_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["get_active_window"].info.name, "get_active_window")
        self.assertIn("fenetre active", tools["get_active_window"].info.description.lower())
        self.assertEqual(tools["focus_window"].info.name, "focus_window")
        self.assertIn("premier plan", tools["focus_window"].info.description.lower())
        self.assertEqual(tools["minimize_window"].info.name, "minimize_window")
        self.assertIn("minimise", tools["minimize_window"].info.description.lower())
        self.assertEqual(tools["maximize_window"].info.name, "maximize_window")
        self.assertIn("sans activer", tools["maximize_window"].info.description.lower())
        self.assertEqual(tools["move_window"].info.name, "move_window")
        self.assertIn("left", tools["move_window"].info.description.lower())

    def test_window_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["get_active_window"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_window_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["move_window"]
            result = asyncio.run(tool("center", "Safari"))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("move_window", ("center", "Safari"))])

    def test_existing_capability_tools_remain_exposed(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("play_pause", tools)
        self.assertIn("get_battery_status", tools)


class LiveFilesToolTest(unittest.TestCase):
    def make_tools(self, security=None, filesystem_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            filesystem_tools=filesystem_tools or RecordingLiveFileSystemTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_list_files_success_returns_structured_result(self):
        filesystem_tools = RecordingLiveFileSystemTools()
        tool = self.make_tools(filesystem_tools=filesystem_tools)["list_files"]

        result = asyncio.run(tool("Documents"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "list_files")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(filesystem_tools.calls, [("list_files", "Documents")])

    def test_find_files_success_returns_structured_result(self):
        filesystem_tools = RecordingLiveFileSystemTools()
        tool = self.make_tools(filesystem_tools=filesystem_tools)["find_files"]

        result = asyncio.run(tool("report", "Downloads"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "find_files")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(
            filesystem_tools.calls,
            [("find_files", "report", "Downloads")],
        )

    def test_get_file_info_success_returns_structured_result(self):
        filesystem_tools = RecordingLiveFileSystemTools()
        tool = self.make_tools(filesystem_tools=filesystem_tools)["get_file_info"]

        result = asyncio.run(tool("/Users/test/report.pdf"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "file")
        self.assertEqual(result["size_bytes"], 42)
        self.assertEqual(
            filesystem_tools.calls,
            [("get_file_info", "/Users/test/report.pdf")],
        )

    def test_open_file_and_folder_preserve_unconfirmed_state(self):
        filesystem_tools = RecordingLiveFileSystemTools()
        tools = self.make_tools(filesystem_tools=filesystem_tools)

        file_result = asyncio.run(tools["open_file"]("/Users/test/report.pdf"))
        folder_result = asyncio.run(tools["open_folder"]("/Users/test/Documents"))

        self.assertTrue(file_result["command_executed"])
        self.assertFalse(file_result["state_confirmed"])
        self.assertTrue(folder_result["command_executed"])
        self.assertFalse(folder_result["state_confirmed"])

    def test_create_rename_and_move_files_use_security(self):
        security = RecordingLiveSecurity()
        filesystem_tools = RecordingLiveFileSystemTools()
        tools = self.make_tools(
            security=security,
            filesystem_tools=filesystem_tools,
        )

        create = asyncio.run(tools["create_folder"]("/Users/test/New"))
        rename = asyncio.run(
            tools["rename_file"]("/Users/test/old.txt", "new.txt")
        )
        move = asyncio.run(
            tools["move_file"]("/Users/test/new.txt", "/Users/test/Done/new.txt")
        )

        self.assertTrue(create["state_confirmed"])
        self.assertTrue(rename["state_confirmed"])
        self.assertTrue(move["state_confirmed"])
        self.assertEqual(
            [intent.action for intent in security.intents],
            ["create_folder", "rename_file", "move_file"],
        )

    def test_files_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["list_files"].info.name, "list_files")
        self.assertIn("dossier", tools["list_files"].info.description.lower())
        self.assertEqual(tools["find_files"].info.name, "find_files")
        self.assertIn("extension", tools["find_files"].info.description.lower())
        self.assertEqual(tools["get_file_info"].info.name, "get_file_info")
        self.assertIn("taille", tools["get_file_info"].info.description.lower())
        self.assertEqual(tools["open_file"].info.name, "open_file")
        self.assertEqual(tools["open_folder"].info.name, "open_folder")
        self.assertEqual(tools["create_folder"].info.name, "create_folder")
        self.assertEqual(tools["rename_file"].info.name, "rename_file")
        self.assertEqual(tools["move_file"].info.name, "move_file")

    def test_file_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["list_files"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_files_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["move_file"]
            result = asyncio.run(tool("/Users/test/a.txt", "/Users/test/b.txt"))

        self.assertTrue(result["ok"])
        self.assertEqual(
            calls,
            [("move_file", ("/Users/test/a.txt", "/Users/test/b.txt"))],
        )

    def test_existing_capability_tools_remain_exposed_with_files(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("play_pause", tools)
        self.assertIn("get_battery_status", tools)
        self.assertIn("get_active_window", tools)


class LiveClipboardToolTest(unittest.TestCase):
    def make_tools(self, security=None, clipboard_tools=None):
        tools = create_live_tools(
            security=security or RecordingLiveSecurity(),
            clipboard_tools=clipboard_tools or RecordingLiveClipboardTools(),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_get_clipboard_text_success_returns_structured_result(self):
        clipboard_tools = RecordingLiveClipboardTools()
        tool = self.make_tools(clipboard_tools=clipboard_tools)["get_clipboard_text"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "get_clipboard_text")
        self.assertEqual(result["text"], "Bonjour")
        self.assertEqual(result["length"], 7)
        self.assertEqual(clipboard_tools.calls, [("get_text",)])

    def test_set_clipboard_text_success_uses_security_and_backend(self):
        security = RecordingLiveSecurity()
        clipboard_tools = RecordingLiveClipboardTools()
        tool = self.make_tools(
            security=security,
            clipboard_tools=clipboard_tools,
        )["set_clipboard_text"]

        result = asyncio.run(tool("Bonjour"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "set_clipboard_text")
        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(security.intents[0].action, "set_clipboard_text")
        self.assertEqual(clipboard_tools.calls, [("set_text", "Bonjour")])

    def test_clipboard_tool_arguments_are_not_modified_by_log_redaction(self):
        secret = "JARVIS_CLIPBOARD_ARGUMENT_SENTINEL_41d4"
        clipboard_tools = RecordingLiveClipboardTools()
        tool = self.make_tools(clipboard_tools=clipboard_tools)[
            "set_clipboard_text"
        ]

        result = asyncio.run(tool(secret))

        self.assertTrue(result["ok"])
        self.assertEqual(clipboard_tools.calls, [("set_text", secret)])

    def test_get_clipboard_text_still_returns_text_to_gemini(self):
        secret = "JARVIS_CLIPBOARD_RESULT_SENTINEL_60bb"
        clipboard_tools = RecordingLiveClipboardTools(
            text_state={
                "has_text": True,
                "text": secret,
                "length": len(secret),
                "returned_length": len(secret),
                "truncated": False,
                "content_type": "text",
            },
        )
        tool = self.make_tools(clipboard_tools=clipboard_tools)[
            "get_clipboard_text"
        ]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], secret)

    def test_clear_clipboard_success_uses_security_and_backend(self):
        security = RecordingLiveSecurity()
        clipboard_tools = RecordingLiveClipboardTools()
        tool = self.make_tools(
            security=security,
            clipboard_tools=clipboard_tools,
        )["clear_clipboard"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "clear_clipboard")
        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(security.intents[0].action, "clear_clipboard")
        self.assertEqual(clipboard_tools.calls, [("clear",)])

    def test_clipboard_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(
            tools["get_clipboard_text"].info.name,
            "get_clipboard_text",
        )
        self.assertIn(
            "presse-papiers",
            tools["get_clipboard_text"].info.description.lower(),
        )
        self.assertEqual(
            tools["set_clipboard_text"].info.name,
            "set_clipboard_text",
        )
        self.assertEqual(
            tools["clear_clipboard"].info.name,
            "clear_clipboard",
        )

    def test_clipboard_tool_returns_awaitable_result_for_livekit(self):
        tool = self.make_tools()["get_clipboard_text"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_clipboard_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["set_clipboard_text"]
            result = asyncio.run(tool("Bonjour"))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("set_clipboard_text", ("Bonjour",))])

    def test_clipboard_tools_share_a_lock_without_affecting_media_lock(self):
        registry = ToolRegistry(
            clipboard_capability=object(),
            media_capability=object(),
        )

        self.assertIsNot(registry.clipboard_lock, registry.media_lock)
        self.assertTrue(hasattr(registry.clipboard_lock, "acquire"))

    def test_clipboard_debug_does_not_log_raw_secret_text(self):
        secret = "JARVIS_CLIPBOARD_SECRET_SENTINEL_7f31"
        clipboard_tools = RecordingLiveClipboardTools(
            text_state={
                "has_text": True,
                "text": secret,
                "length": len(secret),
                "returned_length": len(secret),
                "truncated": False,
                "content_type": "text",
            },
            set_state={
                "command_executed": True,
                "state_confirmed": True,
                "length": len(secret),
                "has_text": True,
                "content_type": "text",
            },
        )
        tools = self.make_tools(clipboard_tools=clipboard_tools)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["get_clipboard_text"]())
                asyncio.run(tools["set_clipboard_text"](secret))

        debug_output = output.getvalue()

        self.assertNotIn(secret, debug_output)
        self.assertIn("get_clipboard_text", debug_output)
        self.assertIn("set_clipboard_text", debug_output)
        self.assertIn(f"length: {len(secret)}", debug_output)

    def test_existing_capability_tools_remain_exposed_with_clipboard(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("play_pause", tools)
        self.assertIn("get_battery_status", tools)
        self.assertIn("get_active_window", tools)
        self.assertIn("list_files", tools)


class LiveKeyboardToolTest(unittest.TestCase):
    def make_tools(self, keyboard_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            keyboard_capability=(
                keyboard_capability or RecordingLiveKeyboardCapability()
            ),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_keyboard_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["type_text"].info.name, "type_text")
        self.assertEqual(tools["press_key"].info.name, "press_key")
        self.assertEqual(tools["hotkey"].info.name, "hotkey")
        self.assertIn("fenetre", tools["type_text"].info.description.lower())
        self.assertIn("raccourci", tools["hotkey"].info.description.lower())
        self.assertIn('["command", "a"]', tools["hotkey"].info.description)

    def test_type_text_success_returns_structured_result_without_confirmation(self):
        capability = RecordingLiveKeyboardCapability()
        tool = self.make_tools(keyboard_capability=capability)["type_text"]

        result = asyncio.run(tool("Bonjour"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "type_text")
        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(result["length"], 7)
        self.assertNotIn("text", result)
        self.assertEqual(capability.calls, [("type_text", "Bonjour")])

    def test_press_key_success_returns_structured_result(self):
        capability = RecordingLiveKeyboardCapability()
        tool = self.make_tools(keyboard_capability=capability)["press_key"]

        result = asyncio.run(tool("enter"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["key"], "enter")
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(capability.calls, [("press_key", "enter")])

    def test_hotkey_success_returns_structured_result(self):
        capability = RecordingLiveKeyboardCapability()
        tool = self.make_tools(keyboard_capability=capability)["hotkey"]

        result = asyncio.run(tool(["command", "a"]))

        self.assertTrue(result["ok"])
        self.assertEqual(result["keys"], ["command", "a"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(capability.calls, [("hotkey", ["command", "a"])])

    def test_keyboard_tools_return_awaitable_result_for_livekit(self):
        tool = self.make_tools()["press_key"]

        result = tool("enter")

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_keyboard_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["hotkey"]
            result = asyncio.run(tool(["command", "a"]))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("hotkey", (["command", "a"],))])

    def test_keyboard_tools_share_a_lock_without_affecting_existing_locks(self):
        registry = ToolRegistry(
            keyboard_capability=object(),
            media_capability=object(),
            clipboard_capability=object(),
        )

        self.assertIsNot(registry.keyboard_lock, registry.media_lock)
        self.assertIsNot(registry.keyboard_lock, registry.clipboard_lock)
        self.assertTrue(hasattr(registry.keyboard_lock, "acquire"))

    def test_keyboard_debug_does_not_log_raw_text(self):
        secret = "JARVIS_KEYBOARD_SECRET_SENTINEL_42a1"
        capability = RecordingLiveKeyboardCapability()
        tools = self.make_tools(keyboard_capability=capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["type_text"](secret))

        debug_output = output.getvalue()

        self.assertNotIn(secret, debug_output)
        self.assertIn("type_text", debug_output)
        self.assertIn(f"length: {len(secret)}", debug_output)

    def test_existing_capability_tools_remain_exposed_with_keyboard(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("get_active_window", tools)
        self.assertIn("get_clipboard_text", tools)


class LiveMouseToolTest(unittest.TestCase):
    def make_tools(self, mouse_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            mouse_capability=(
                mouse_capability or RecordingLiveMouseCapability()
            ),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_mouse_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["get_mouse_position"].info.name, "get_mouse_position")
        self.assertEqual(tools["move_mouse"].info.name, "move_mouse")
        self.assertEqual(tools["click"].info.name, "click")
        self.assertEqual(tools["double_click"].info.name, "double_click")
        self.assertEqual(tools["right_click"].info.name, "right_click")
        self.assertEqual(tools["scroll"].info.name, "scroll")
        self.assertIn("coordonnees", tools["move_mouse"].info.description.lower())
        self.assertIn("up", tools["scroll"].info.description)
        self.assertIn("down", tools["scroll"].info.description)

    def test_get_mouse_position_success_returns_structured_result(self):
        capability = RecordingLiveMouseCapability()
        tool = self.make_tools(mouse_capability=capability)["get_mouse_position"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "get_mouse_position")
        self.assertEqual(result["x"], 10)
        self.assertEqual(result["y"], 20)
        self.assertEqual(result["screen_index"], 0)
        self.assertEqual(capability.calls, [("get_mouse_position",)])

    def test_move_mouse_success_returns_structured_result(self):
        capability = RecordingLiveMouseCapability()
        tool = self.make_tools(mouse_capability=capability)["move_mouse"]

        result = asyncio.run(tool(100, 200))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "move_mouse")
        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(result["target_x"], 100)
        self.assertEqual(result["target_y"], 200)
        self.assertEqual(capability.calls, [("move_mouse", 100, 200)])

    def test_click_tools_return_unconfirmed_results(self):
        capability = RecordingLiveMouseCapability()
        tools = self.make_tools(mouse_capability=capability)

        click = asyncio.run(tools["click"]())
        double_click = asyncio.run(tools["double_click"]())
        right_click = asyncio.run(tools["right_click"]())

        self.assertFalse(click["state_confirmed"])
        self.assertEqual(click["button"], "left")
        self.assertEqual(click["click_count"], 1)
        self.assertEqual(double_click["click_count"], 2)
        self.assertEqual(right_click["button"], "right")
        self.assertEqual(
            capability.calls,
            [("click",), ("double_click",), ("right_click",)],
        )

    def test_scroll_success_returns_structured_result(self):
        capability = RecordingLiveMouseCapability()
        tool = self.make_tools(mouse_capability=capability)["scroll"]

        result = asyncio.run(tool("down", 4))

        self.assertTrue(result["ok"])
        self.assertEqual(result["direction"], "down")
        self.assertEqual(result["amount"], 4)
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(capability.calls, [("scroll", "down", 4)])

    def test_mouse_tools_return_awaitable_result_for_livekit(self):
        tool = self.make_tools()["get_mouse_position"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_mouse_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["move_mouse"]
            result = asyncio.run(tool(100, 200))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("move_mouse", (100, 200))])

    def test_mouse_tools_share_a_lock_without_affecting_existing_locks(self):
        registry = ToolRegistry(
            mouse_capability=object(),
            keyboard_capability=object(),
            media_capability=object(),
            clipboard_capability=object(),
        )

        self.assertIsNot(registry.mouse_lock, registry.keyboard_lock)
        self.assertIsNot(registry.mouse_lock, registry.media_lock)
        self.assertIsNot(registry.mouse_lock, registry.clipboard_lock)
        self.assertTrue(hasattr(registry.mouse_lock, "acquire"))

    def test_mouse_debug_logs_only_metadata(self):
        capability = RecordingLiveMouseCapability()
        tools = self.make_tools(mouse_capability=capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["scroll"]("down", 4))

        debug_output = output.getvalue()

        self.assertIn("scroll", debug_output)
        self.assertIn("direction: down", debug_output)
        self.assertIn("amount: 4", debug_output)
        self.assertIn("state_confirmed: False", debug_output)

    def test_existing_capability_tools_remain_exposed_with_mouse(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("get_active_window", tools)
        self.assertIn("type_text", tools)


class LiveUIAccessibilityToolTest(unittest.TestCase):
    def make_tools(self, ui_accessibility_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            ui_accessibility_capability=(
                ui_accessibility_capability
                or RecordingLiveUIAccessibilityCapability()
            ),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_ui_accessibility_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(tools["inspect_ui"].info.name, "inspect_ui")
        self.assertEqual(tools["find_ui_elements"].info.name, "find_ui_elements")
        self.assertEqual(tools["focus_ui_element"].info.name, "focus_ui_element")
        self.assertEqual(tools["activate_ui_element"].info.name, "activate_ui_element")
        self.assertIn("Accessibility", tools["inspect_ui"].info.description)
        self.assertIn("AXPress", tools["activate_ui_element"].info.description)

    def test_inspect_ui_success_returns_structured_result(self):
        capability = RecordingLiveUIAccessibilityCapability()
        tool = self.make_tools(ui_accessibility_capability=capability)["inspect_ui"]

        result = asyncio.run(tool(3, 20))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "inspect_ui")
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["truncated"])
        self.assertEqual(capability.calls, [("inspect_ui", 3, 20)])

    def test_find_ui_elements_uses_query_but_debug_uses_length(self):
        capability = RecordingLiveUIAccessibilityCapability()
        tool = self.make_tools(ui_accessibility_capability=capability)["find_ui_elements"]

        result = asyncio.run(tool("Secret label", "AXButton"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["query_length"], len("Secret label"))
        self.assertEqual(
            capability.calls,
            [("find_ui_elements", "Secret label", "AXButton")],
        )

    def test_focus_and_activate_return_command_state(self):
        capability = RecordingLiveUIAccessibilityCapability()
        tools = self.make_tools(ui_accessibility_capability=capability)

        focus = asyncio.run(tools["focus_ui_element"]("Recherche", "AXTextField"))
        activate = asyncio.run(tools["activate_ui_element"]("Continuer", "AXButton"))

        self.assertTrue(focus["state_confirmed"])
        self.assertTrue(activate["command_executed"])
        self.assertFalse(activate["state_confirmed"])
        self.assertEqual(
            capability.calls,
            [
                ("focus_ui_element", "Recherche", "AXTextField"),
                ("activate_ui_element", "Continuer", "AXButton"),
            ],
        )

    def test_ui_accessibility_tools_return_awaitable_result_for_livekit(self):
        tool = self.make_tools()["inspect_ui"]

        result = tool()

        self.assertTrue(hasattr(result, "__await__"))
        self.assertTrue(asyncio.run(result)["ok"])

    def test_live_tools_use_to_thread_for_ui_accessibility_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["activate_ui_element"]
            result = asyncio.run(tool("Continuer", "AXButton"))

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("activate_ui_element", ("Continuer", "AXButton"))])

    def test_ui_tools_share_a_lock_without_affecting_existing_locks(self):
        registry = ToolRegistry(
            ui_accessibility_capability=object(),
            mouse_capability=object(),
            keyboard_capability=object(),
            media_capability=object(),
            clipboard_capability=object(),
        )

        self.assertIsNot(registry.ui_lock, registry.mouse_lock)
        self.assertIsNot(registry.ui_lock, registry.keyboard_lock)
        self.assertIsNot(registry.ui_lock, registry.media_lock)
        self.assertIsNot(registry.ui_lock, registry.clipboard_lock)
        self.assertTrue(hasattr(registry.ui_lock, "acquire"))

    def test_ui_debug_does_not_log_raw_query_or_labels(self):
        secret = "JARVIS_UI_SECRET_LABEL_8d13"
        capability = RecordingLiveUIAccessibilityCapability()
        tools = self.make_tools(ui_accessibility_capability=capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["find_ui_elements"](secret, "AXButton"))

        debug_output = output.getvalue()

        self.assertNotIn(secret, debug_output)
        self.assertIn("find_ui_elements", debug_output)
        self.assertIn(f"query_length: {len(secret)}", debug_output)

    def test_existing_capability_tools_remain_exposed_with_ui_accessibility(self):
        tools = self.make_tools()

        self.assertIn("get_volume", tools)
        self.assertIn("open_app", tools)
        self.assertIn("get_active_window", tools)
        self.assertIn("type_text", tools)
        self.assertIn("click", tools)


class LiveInteractionToolTest(unittest.TestCase):
    def make_tools(self, interaction_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            interaction_capability=(
                interaction_capability
                or RecordingLiveInteractionCapability()
            ),
        )
        return {
            tool.info.name: tool
            for tool in tools
        }

    def test_interaction_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        self.assertEqual(
            tools["select_all_and_copy"].info.name,
            "select_all_and_copy",
        )
        self.assertEqual(
            tools["focus_app_ui_and_type"].info.name,
            "focus_app_ui_and_type",
        )
        self.assertEqual(
            tools["open_app_and_focus_ui"].info.name,
            "open_app_and_focus_ui",
        )
        self.assertIn("command+a", tools["select_all_and_copy"].info.description)
        self.assertIn("saisit du texte", tools["focus_app_ui_and_type"].info.description)
        description = tools["focus_app_ui_and_type"].info.description
        self.assertIn("obligatoirement query", description)
        self.assertIn("query=None", description)
        self.assertIn("editable_target_not_verified", description)
        self.assertIn("aucune saisie ni Enter", description)
        self.assertIn("sans taper", tools["open_app_and_focus_ui"].info.description)

    def test_select_all_and_copy_success_returns_structured_steps(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["select_all_and_copy"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "select_all_and_copy")
        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(capability.calls, [("select_all_and_copy",)])

    def test_select_all_and_delete_is_named_and_distinct_from_copy(self):
        tools = self.make_tools()

        self.assertEqual(
            tools["select_all_and_delete"].info.name,
            "select_all_and_delete",
        )
        description = tools["select_all_and_delete"].info.description
        self.assertIn("supprime", description)
        self.assertIn("jamais select_all_and_copy", description)
        self.assertNotIn("supprime", tools["select_all_and_copy"].info.description)

    def test_select_all_and_delete_routes_to_capability(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["select_all_and_delete"]

        result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "select_all_and_delete")
        self.assertFalse(result["state_confirmed"])
        self.assertTrue(result["deletion_executed"])
        self.assertEqual(capability.calls, [("select_all_and_delete",)])

    def test_send_prompt_to_app_submits_via_focus_app_ui_and_type(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["send_prompt_to_app"]

        # A non-direct-type app uses the AX-verified flow with press_enter=True.
        result = asyncio.run(tool("Notes", "Explique la relativite"))

        self.assertTrue(result["ok"])
        self.assertEqual(
            capability.calls,
            [("focus_app_ui_and_type", "Notes", "Explique la relativite", None, None, True)],
        )

    def test_send_prompt_to_app_claude_types_directly(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["send_prompt_to_app"]

        result = asyncio.run(tool("Claude", "Explique la relativite"))

        self.assertTrue(result["ok"])
        # Electron app → direct type, no AX field verification.
        self.assertEqual(
            capability.calls,
            [("open_app_and_type", "Claude", "Explique la relativite", True)],
        )

    def test_send_prompt_to_app_other_app_uses_ax_verified_path(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["send_prompt_to_app"]

        result = asyncio.run(tool("TextEdit", "Bonjour"))

        self.assertTrue(result["ok"])
        self.assertEqual(capability.calls[0][0], "focus_app_ui_and_type")

    def test_send_prompt_to_app_explicit_query_overrides_direct_type(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["send_prompt_to_app"]

        result = asyncio.run(tool("Claude", "Salut", "un champ"))

        self.assertTrue(result["ok"])
        # Explicit query → AX-verified path even for a direct-type app.
        self.assertEqual(capability.calls[0][0], "focus_app_ui_and_type")

    def test_send_prompt_to_app_description_mentions_claude_and_submit(self):
        tools = self.make_tools()
        description = tools["send_prompt_to_app"].info.description
        self.assertIn("Claude", description)
        self.assertIn("Entree", description)

    def test_interaction_debug_never_logs_arbitrary_data_fields(self):
        class LeakyInteraction:
            def select_all_and_copy(self):
                return ToolResult.success(
                    action="select_all_and_copy",
                    message="ok",
                    command_executed=True,
                    state_confirmed=False,
                    text="CLIPBOARD_SECRET_CONTENT",
                    steps=[{"name": "get_clipboard_text_after", "ok": True}],
                )

        tools = self.make_tools(interaction_capability=LeakyInteraction())

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["select_all_and_copy"]())

        self.assertNotIn("CLIPBOARD_SECRET_CONTENT", output.getvalue())

    def test_focus_app_ui_and_type_uses_text_but_debug_uses_length(self):
        secret_text = "JARVIS_INTERACTION_SECRET_TEXT"
        secret_query = "JARVIS_INTERACTION_SECRET_QUERY"
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(interaction_capability=capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                result = asyncio.run(
                    tools["focus_app_ui_and_type"](
                        "Safari",
                        secret_text,
                        secret_query,
                        "AXTextField",
                        True,
                    )
                )

        debug_output = output.getvalue()

        self.assertTrue(result["ok"])
        self.assertEqual(result["text_length"], len(secret_text))
        self.assertEqual(result["query_length"], len(secret_query))
        self.assertEqual(
            capability.calls,
            [(
                "focus_app_ui_and_type",
                "Safari",
                secret_text,
                secret_query,
                "AXTextField",
                True,
            )],
        )
        self.assertNotIn(secret_text, debug_output)
        self.assertNotIn(secret_query, debug_output)
        self.assertIn(f"text_length: {len(secret_text)}", debug_output)
        self.assertIn(f"query_length: {len(secret_query)}", debug_output)

    def test_open_app_and_focus_ui_returns_confirmed_state(self):
        capability = RecordingLiveInteractionCapability()
        tool = self.make_tools(interaction_capability=capability)["open_app_and_focus_ui"]

        result = asyncio.run(tool("Safari", "barre de recherche", "AXTextField"))

        self.assertTrue(result["ok"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(result["query_length"], len("barre de recherche"))
        self.assertEqual(
            capability.calls,
            [("open_app_and_focus_ui", "Safari", "barre de recherche", "AXTextField")],
        )

    def test_live_tools_use_to_thread_for_interaction_capability(self):
        calls = []

        async def fake_to_thread(func, *args):
            calls.append((func.__name__, args))
            return func(*args)

        with patch("jarvis.live.registry.asyncio.to_thread", fake_to_thread):
            tool = self.make_tools()["select_all_and_copy"]
            result = asyncio.run(tool())

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("select_all_and_copy", ())])

    def test_interaction_tools_share_a_lock_without_affecting_existing_locks(self):
        registry = ToolRegistry(
            interaction_capability=object(),
            ui_accessibility_capability=object(),
            mouse_capability=object(),
            keyboard_capability=object(),
            media_capability=object(),
            clipboard_capability=object(),
        )

        self.assertIsNot(registry.interaction_lock, registry.ui_lock)
        self.assertIsNot(registry.interaction_lock, registry.mouse_lock)
        self.assertIsNot(registry.interaction_lock, registry.keyboard_lock)
        self.assertIsNot(registry.interaction_lock, registry.clipboard_lock)
        self.assertTrue(hasattr(registry.interaction_lock, "acquire"))


class RecordingLiveBrowserCapability:
    def __init__(self):
        self.calls = []

    def open_url(self, url, browser=None, new_tab=True):
        self.calls.append(("open_url", url, browser, new_tab))
        return ToolResult.success(
            action="open_url",
            message="La page est affichee.",
            browser=browser or "Safari",
            requested_url=url,
            active_url="https://example.com/",
            active_title="Example",
            new_tab=new_tab,
            command_executed=True,
            state_confirmed=True,
        )

    def search_web(self, query, browser=None, engine=None):
        self.calls.append(("search_web", query, browser, engine))
        return ToolResult.success(
            action="search_web",
            message="Recherche lancee.",
            browser=browser or "Safari",
            active_url="https://www.google.com/search?q=x",
            query_length=len(query) if isinstance(query, str) else None,
            engine=engine or "google",
            command_executed=True,
            state_confirmed=True,
        )

    def get_active_tab(self, browser=None):
        self.calls.append(("get_active_tab", browser))
        return ToolResult.success(
            action="get_active_tab",
            message="Onglet lu.",
            browser=browser or "Safari",
            has_window=True,
            url="https://example.com/",
            title="Example",
        )

    def list_tabs(self, browser=None):
        self.calls.append(("list_tabs", browser))
        return ToolResult.success(
            action="list_tabs",
            message="2 onglets.",
            browser=browser or "Safari",
            active_index=1,
            tabs=[],
            count=2,
        )

    def activate_tab(self, query=None, index=None, browser=None):
        self.calls.append(("activate_tab", query, index, browser))
        return ToolResult.success(
            action="activate_tab",
            message="Onglet active.",
            browser=browser or "Safari",
            query_length=len(query) if isinstance(query, str) else None,
            active_index=index,
            command_executed=True,
            state_confirmed=True,
        )


class LiveBrowserToolTest(unittest.TestCase):
    def make_tools(self, browser_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            browser_capability=browser_capability or RecordingLiveBrowserCapability(),
        )
        return {tool.info.name: tool for tool in tools}

    def test_browser_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        for name in (
            "browse_open_url",
            "browse_search_web",
            "browse_get_active_tab",
            "browse_list_tabs",
            "browse_activate_tab",
        ):
            self.assertEqual(tools[name].info.name, name)

        self.assertIn("state_confirmed", tools["browse_open_url"].info.description)
        self.assertIn("ambiguous_tab", tools["browse_activate_tab"].info.description)

    def test_browse_open_url_routes_to_capability(self):
        capability = RecordingLiveBrowserCapability()
        tool = self.make_tools(capability)["browse_open_url"]

        result = asyncio.run(tool("youtube.com", "Safari", True))

        self.assertTrue(result["ok"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(
            capability.calls,
            [("open_url", "youtube.com", "Safari", True)],
        )

    def test_browse_search_web_routes_to_capability(self):
        capability = RecordingLiveBrowserCapability()
        tool = self.make_tools(capability)["browse_search_web"]

        result = asyncio.run(tool("meteo paris", None, "duckduckgo"))

        self.assertTrue(result["ok"])
        self.assertEqual(
            capability.calls,
            [("search_web", "meteo paris", None, "duckduckgo")],
        )

    def test_browse_activate_tab_routes_query_to_capability(self):
        capability = RecordingLiveBrowserCapability()
        tool = self.make_tools(capability)["browse_activate_tab"]

        result = asyncio.run(tool("github"))

        self.assertTrue(result["ok"])
        self.assertEqual(capability.calls, [("activate_tab", "github", None, None)])

    def test_browse_activate_tab_routes_explicit_index_to_capability(self):
        capability = RecordingLiveBrowserCapability()
        tool = self.make_tools(capability)["browse_activate_tab"]

        result = asyncio.run(tool(None, 8))

        self.assertTrue(result["ok"])
        self.assertEqual(result["active_index"], 8)
        self.assertEqual(capability.calls, [("activate_tab", None, 8, None)])

    def test_browser_debug_logs_host_not_full_url_or_query(self):
        capability = RecordingLiveBrowserCapability()
        tools = self.make_tools(capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["browse_search_web"]("SECRET_QUERY_TEXT", None, None))

        debug_output = output.getvalue()

        self.assertNotIn("SECRET_QUERY_TEXT", debug_output)
        self.assertNotIn("https://www.google.com/search", debug_output)
        self.assertIn("active_host", debug_output)

    def test_browser_has_its_own_lock(self):
        registry = ToolRegistry(
            browser_capability=object(),
            interaction_capability=object(),
        )

        self.assertIsNot(registry.browser_lock, registry.interaction_lock)
        self.assertTrue(hasattr(registry.browser_lock, "acquire"))


class RecordingLiveScreenshotCapability:
    def __init__(self):
        self.calls = []

    def capture_screen(self, path=None, display=None):
        self.calls.append(("capture_screen", path, display))
        return ToolResult.success(
            action="capture_screen",
            message="Capture enregistree.",
            path="/Users/someone/Pictures/Jarvis/jarvis-screenshot-x.png",
            bytes=4096,
            width=1440,
            height=900,
            command_executed=True,
            state_confirmed=True,
        )

    def capture_region(self, x, y, width, height, path=None):
        self.calls.append(("capture_region", x, y, width, height, path))
        return ToolResult.success(
            action="capture_region",
            message="Capture enregistree.",
            path="/Users/someone/Pictures/Jarvis/region.png",
            bytes=1024,
            width=width,
            height=height,
            region={"x": x, "y": y, "width": width, "height": height},
            command_executed=True,
            state_confirmed=True,
        )

    def capture_window(self, app_name=None, path=None):
        self.calls.append(("capture_window", app_name, path))
        return ToolResult.success(
            action="capture_window",
            message="Capture enregistree.",
            path="/Users/someone/Pictures/Jarvis/window.png",
            bytes=2048,
            target_app=app_name or "Safari",
            command_executed=True,
            state_confirmed=True,
        )


class LiveScreenshotToolTest(unittest.TestCase):
    def make_tools(self, screenshot_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            screenshot_capability=(
                screenshot_capability or RecordingLiveScreenshotCapability()
            ),
        )
        return {tool.info.name: tool for tool in tools}

    def test_screenshot_tools_are_named_for_gemini(self):
        tools = self.make_tools()

        for name in ("capture_screen", "capture_region", "capture_window"):
            self.assertEqual(tools[name].info.name, name)

        self.assertIn("ne contient pas l'image", tools["capture_screen"].info.description)
        self.assertIn("coordonnees", tools["capture_region"].info.description)

    def test_capture_screen_routes_to_capability(self):
        capability = RecordingLiveScreenshotCapability()
        tool = self.make_tools(capability)["capture_screen"]

        result = asyncio.run(tool(None, 1))

        self.assertTrue(result["ok"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(capability.calls, [("capture_screen", None, 1)])

    def test_capture_region_routes_to_capability(self):
        capability = RecordingLiveScreenshotCapability()
        tool = self.make_tools(capability)["capture_region"]

        result = asyncio.run(tool(10, 20, 30, 40, None))

        self.assertTrue(result["ok"])
        self.assertEqual(
            capability.calls,
            [("capture_region", 10, 20, 30, 40, None)],
        )

    def test_capture_window_routes_to_capability(self):
        capability = RecordingLiveScreenshotCapability()
        tool = self.make_tools(capability)["capture_window"]

        result = asyncio.run(tool("Notes", None))

        self.assertTrue(result["ok"])
        self.assertEqual(capability.calls, [("capture_window", "Notes", None)])

    def test_screenshot_debug_logs_basename_not_full_path(self):
        capability = RecordingLiveScreenshotCapability()
        tools = self.make_tools(capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()

            with redirect_stdout(output):
                asyncio.run(tools["capture_screen"](None, None))

        debug_output = output.getvalue()

        self.assertNotIn("/Users/someone/Pictures/Jarvis", debug_output)
        self.assertIn("jarvis-screenshot-x.png", debug_output)

    def test_screenshot_has_its_own_lock(self):
        registry = ToolRegistry(
            screenshot_capability=object(),
            browser_capability=object(),
        )

        self.assertIsNot(registry.screenshot_lock, registry.browser_lock)
        self.assertTrue(hasattr(registry.screenshot_lock, "acquire"))


class RecordingLiveVisionCapability:
    def __init__(self, analysis="Une page web est affichee.", question_length=None):
        self.analysis = analysis
        self.question_length = question_length
        self.calls = []

    def describe_screen(self, target="window", app_name=None):
        self.calls.append(("describe_screen", target, app_name))
        return ToolResult.success(
            action="describe_screen",
            message=self.analysis,
            analysis=self.analysis,
            source=target,
            model="gemini-2.5-flash",
            image_path="/Users/someone/Pictures/Jarvis/shot.png",
            image_bytes=1234,
            image_width=3024,
            image_height=1964,
            duration_ms=42,
        )

    def ask_about_screen(self, question, target="window", app_name=None):
        self.calls.append(("ask_about_screen", question, target, app_name))
        return ToolResult.success(
            action="ask_about_screen",
            message=self.analysis,
            analysis=self.analysis,
            source=target,
            model="gemini-2.5-flash",
            question_length=len(question) if isinstance(question, str) else None,
            image_path="/Users/someone/Pictures/Jarvis/shot.png",
            image_bytes=1234,
            duration_ms=42,
        )


class LiveVisionToolTest(unittest.TestCase):
    def make_tools(self, vision_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            vision_capability=vision_capability or RecordingLiveVisionCapability(),
        )
        return {tool.info.name: tool for tool in tools}

    def test_vision_tools_are_named_and_read_only(self):
        tools = self.make_tools()

        self.assertEqual(tools["describe_screen"].info.name, "describe_screen")
        self.assertEqual(tools["ask_about_screen"].info.name, "ask_about_screen")
        for name in ("describe_screen", "ask_about_screen"):
            description = tools[name].info.description
            self.assertIn("Accessibility", description)
            self.assertIn("coordonnee", description)

    def test_describe_screen_routes_when_enabled(self):
        capability = RecordingLiveVisionCapability()
        tool = self.make_tools(capability)["describe_screen"]

        with patch.dict(os.environ, {"JARVIS_VISION_ENABLED": "1"}, clear=True):
            result = asyncio.run(tool("screen", None))

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "screen")
        self.assertEqual(capability.calls, [("describe_screen", "screen", None)])

    def test_ask_about_screen_routes_when_enabled(self):
        capability = RecordingLiveVisionCapability()
        tool = self.make_tools(capability)["ask_about_screen"]

        with patch.dict(os.environ, {"JARVIS_VISION_ENABLED": "1"}, clear=True):
            result = asyncio.run(tool("Quelle temperature ?", "window", None))

        self.assertTrue(result["ok"])
        self.assertEqual(
            capability.calls,
            [("ask_about_screen", "Quelle temperature ?", "window", None)],
        )

    def test_vision_disabled_blocks_without_capturing(self):
        capability = RecordingLiveVisionCapability()
        tool = self.make_tools(capability)["describe_screen"]

        with patch.dict(os.environ, {}, clear=True):  # JARVIS_VISION_ENABLED unset
            result = asyncio.run(tool("window", None))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "vision_disabled")
        self.assertEqual(capability.calls, [])  # capability never invoked

    def test_vision_debug_logs_metadata_not_analysis_or_question(self):
        capability = RecordingLiveVisionCapability(analysis="SECRET_ANALYSIS_TEXT")
        tools = self.make_tools(capability)

        with patch.dict(
            os.environ,
            {"JARVIS_VISION_ENABLED": "1", "JARVIS_DEBUG_LIVE": "1"},
            clear=True,
        ):
            output = StringIO()
            with redirect_stdout(output):
                asyncio.run(tools["ask_about_screen"]("SECRET_QUESTION_TEXT", "window", None))

        debug_output = output.getvalue()

        self.assertNotIn("SECRET_ANALYSIS_TEXT", debug_output)
        self.assertNotIn("SECRET_QUESTION_TEXT", debug_output)
        self.assertNotIn("/Users/someone/Pictures/Jarvis", debug_output)
        self.assertIn("shot.png", debug_output)
        self.assertIn("gemini-2.5-flash", debug_output)

    def test_vision_has_its_own_lock(self):
        registry = ToolRegistry(
            vision_capability=object(),
            screenshot_capability=object(),
        )

        self.assertIsNot(registry.vision_lock, registry.screenshot_lock)
        self.assertTrue(hasattr(registry.vision_lock, "acquire"))


class RecordingLiveMessagingCapability:
    def __init__(self, verified=True, composer="ChatBar_ComposerTextView"):
        self.verified = verified
        self.composer = composer
        self.calls = []

    def composer_query(self, app_name):
        if isinstance(app_name, str) and app_name.strip().casefold() == "whatsapp":
            return self.composer
        return None

    def supports_composer_send(self, app_name):
        return bool(self.composer_query(app_name))

    def send_text(self, app_name, text):
        self.calls.append(("send_text", app_name, text))
        return ToolResult.success(
            action="send_text",
            message="Message envoye.",
            command_executed=True,
            state_confirmed=True,
            app=app_name,
            text_length=len(text),
        )

    def ensure_recipient(self, app_name, expected_recipient):
        self.calls.append(("ensure_recipient", app_name, expected_recipient))
        if self.verified:
            return ToolResult.success(
                action="verify_recipient",
                message="Destinataire verifie.",
                recipient_verified=True,
                target_app=app_name,
                recipient_length=len(expected_recipient),
            )
        return ToolResult(
            ok=False,
            action="verify_recipient",
            message="La conversation ouverte ne correspond pas.",
            data={"recipient_verified": False, "reason": "recipient_not_visible"},
            error_code="recipient_not_verified",
        )


class LiveConfirmationToolTest(unittest.TestCase):
    def make_tools(self, interaction_capability=None, messaging_capability=None):
        tools = create_live_tools(
            security=RecordingLiveSecurity(),
            interaction_capability=(
                interaction_capability or RecordingLiveInteractionCapability()
            ),
            messaging_capability=(
                messaging_capability or RecordingLiveMessagingCapability()
            ),
        )
        return {tool.info.name: tool for tool in tools}

    def test_confirmation_tools_are_named(self):
        tools = self.make_tools()

        for name in ("prepare_send_message", "confirm_action", "cancel_action"):
            self.assertEqual(tools[name].info.name, name)

        self.assertIn("token", tools["confirm_action"].info.description)
        self.assertIn("SANS l'envoyer", tools["prepare_send_message"].info.description)

    def test_prepare_does_not_send(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        result = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))

        self.assertTrue(result["ok"])
        self.assertTrue(result["requires_confirmation"])
        self.assertIn("token", result)
        self.assertEqual(result["target_app"], "WhatsApp")
        self.assertEqual(capability.calls, [])  # nothing sent yet

    def test_confirm_executes_the_prepared_send(self):
        interaction = RecordingLiveInteractionCapability()
        messaging = RecordingLiveMessagingCapability()
        tools = self.make_tools(interaction, messaging)

        prepared = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut", None))
        result = asyncio.run(tools["confirm_action"](prepared["token"]))

        self.assertTrue(result["ok"])
        # WhatsApp supports the verified composer-send path (write + read back +
        # press send), which the WhatsApp composer needs since it never confirms
        # programmatic focus. The focus + type path is not used.
        self.assertEqual(messaging.calls[-1], ("send_text", "WhatsApp", "Salut"))
        self.assertEqual(interaction.calls, [])

    def test_explicit_query_overrides_composer_default(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        prepared = asyncio.run(
            tools["prepare_send_message"]("WhatsApp", "Salut", None, "Champ custom")
        )
        asyncio.run(tools["confirm_action"](prepared["token"]))

        self.assertEqual(capability.calls[0][3], "Champ custom")

    def test_confirm_is_single_use(self):
        messaging = RecordingLiveMessagingCapability()
        tools = self.make_tools(messaging_capability=messaging)

        prepared = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))
        token = prepared["token"]
        asyncio.run(tools["confirm_action"](token))
        second = asyncio.run(tools["confirm_action"](token))

        self.assertFalse(second["ok"])
        self.assertEqual(second["error_code"], "no_pending_action")
        sends = [call for call in messaging.calls if call[0] == "send_text"]
        self.assertEqual(len(sends), 1)  # executed only once

    def test_confirm_unknown_token_sends_nothing(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        result = asyncio.run(tools["confirm_action"]("not-a-real-token"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "no_pending_action")
        self.assertEqual(capability.calls, [])

    def test_cancel_prevents_send(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        prepared = asyncio.run(tools["prepare_send_message"]("WhatsApp", "Salut"))
        token = prepared["token"]
        cancelled = asyncio.run(tools["cancel_action"](token))
        confirmed = asyncio.run(tools["confirm_action"](token))

        self.assertTrue(cancelled["ok"])
        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(confirmed["error_code"], "no_pending_action")
        self.assertEqual(capability.calls, [])  # never sent

    def test_prepare_rejects_empty_message(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        result = asyncio.run(tools["prepare_send_message"]("WhatsApp", "   "))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_text")
        self.assertNotIn("token", result)

    def test_confirmation_debug_never_logs_message_text(self):
        capability = RecordingLiveInteractionCapability()
        tools = self.make_tools(capability)

        with patch.dict(os.environ, {"JARVIS_DEBUG_LIVE": "1"}, clear=True):
            output = StringIO()
            with redirect_stdout(output):
                prepared = asyncio.run(
                    tools["prepare_send_message"]("WhatsApp", "SECRET_MSG_TEXT")
                )
                asyncio.run(tools["confirm_action"](prepared["token"]))

        debug_output = output.getvalue()
        self.assertNotIn("SECRET_MSG_TEXT", debug_output)
        self.assertIn("text_length: 15", debug_output)

    def test_prepare_with_verified_recipient_prepares_without_sending(self):
        interaction = RecordingLiveInteractionCapability()
        messaging = RecordingLiveMessagingCapability(verified=True)
        tools = self.make_tools(interaction, messaging)

        result = asyncio.run(
            tools["prepare_send_message"]("WhatsApp", "Salut", "Kevin")
        )

        self.assertTrue(result["ok"])
        self.assertIn("token", result)
        self.assertEqual(messaging.calls, [("ensure_recipient", "WhatsApp", "Kevin")])
        self.assertEqual(interaction.calls, [])  # verified, but not sent yet

    def test_prepare_with_unverified_recipient_refuses(self):
        interaction = RecordingLiveInteractionCapability()
        messaging = RecordingLiveMessagingCapability(verified=False)
        tools = self.make_tools(interaction, messaging)

        result = asyncio.run(
            tools["prepare_send_message"]("WhatsApp", "Salut", "Kevin")
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "recipient_not_verified")
        self.assertNotIn("token", result)
        self.assertEqual(interaction.calls, [])  # nothing prepared or sent

    def test_confirmation_has_its_own_lock(self):
        registry = ToolRegistry(interaction_capability=object())

        self.assertTrue(hasattr(registry.confirmation_lock, "acquire"))
        self.assertIsNot(registry.confirmation_lock, registry.interaction_lock)


if __name__ == "__main__":
    unittest.main()
