"""Live POC: volume and application tools."""
import asyncio
import unittest
from unittest.mock import patch

from jarvis.live.tools import create_live_tools
from live_poc_fakes_core import RecordingLiveSecurity
from live_poc_fakes_macos import RecordingLiveMacOSTools


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
