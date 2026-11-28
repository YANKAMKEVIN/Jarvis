"""Live POC: media and system tools."""
import asyncio
import unittest
from unittest.mock import patch

from jarvis.live.tools import create_live_tools
from live_poc_fakes_core import RecordingLiveSecurity
from live_poc_fakes_macos import RecordingLiveMacOSTools


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
        # The two media calls serialize on the shared media lock: neither
        # interleaves with the other (each start is immediately followed by its
        # own end). Which one runs first is not guaranteed -- next_track now also
        # acquires the desktop lease, so get_media_state (a read) may reach the
        # lock first. The invariant under test is serialization, not order.
        self.assertEqual(len(order), 4)
        self.assertEqual(order[0].split(":")[0], "start")
        self.assertEqual(order[1].split(":")[0], "end")
        self.assertEqual(order[0].split(":")[1], order[1].split(":")[1])
        self.assertEqual(order[2].split(":")[0], "start")
        self.assertEqual(order[3].split(":")[0], "end")
        self.assertEqual(order[2].split(":")[1], order[3].split(":")[1])
        self.assertEqual({order[0].split(":")[1], order[2].split(":")[1]},
                         {"next_track", "get_media_state"})

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
