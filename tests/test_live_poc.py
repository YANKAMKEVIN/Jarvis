import asyncio
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
from jarvis.live.prompts import LIVE_SYSTEM_PROMPT
from jarvis.live.tools import ToolRegistry, create_live_tools
from jarvis.security import SecurityDecision
from jarvis.voice_mode import VoiceMode


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
    def __init__(self, error=None, volume=40, get_error=None):
        self.error = error
        self.volume = volume
        self.get_error = get_error
        self.calls = []
        self.get_calls = 0

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
            ["get_volume", "set_volume"],
        )

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

    def test_tool_registry_exposes_audio_tools(self):
        registry = ToolRegistry(
            audio_capability=object(),
        )

        tools = registry.livekit_tools()

        self.assertEqual(
            sorted(tool.info.name for tool in tools),
            ["get_volume", "set_volume"],
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


if __name__ == "__main__":
    unittest.main()
