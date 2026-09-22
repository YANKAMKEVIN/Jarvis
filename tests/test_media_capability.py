import unittest

from jarvis.capabilities.media import MediaCapability
from jarvis.security import SecurityDecision


class RecordingSecurity:
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


class RecordingMacOSTools:
    def __init__(
        self,
        state=None,
        play_error=None,
        next_error=None,
        previous_error=None,
        state_error=None,
    ):
        self.state = state or {
            "media_available": True,
            "playing": True,
            "title": "Song",
            "artist": "Artist",
            "app": "Music",
        }
        self.play_error = play_error
        self.next_error = next_error
        self.previous_error = previous_error
        self.state_error = state_error
        self.play_calls = 0
        self.next_calls = 0
        self.previous_calls = 0
        self.state_calls = 0

    def play_pause(self):
        self.play_calls += 1

        if self.play_error is not None:
            raise self.play_error

        return dict(self.state)

    def next_track(self):
        self.next_calls += 1

        if self.next_error is not None:
            raise self.next_error

        return dict(self.state)

    def previous_track(self):
        self.previous_calls += 1

        if self.previous_error is not None:
            raise self.previous_error

        return dict(self.state)

    def get_media_state(self):
        self.state_calls += 1

        if self.state_error is not None:
            raise self.state_error

        return dict(self.state)


class MediaCapabilityTest(unittest.TestCase):
    def test_play_pause_success_uses_security_then_macos(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = MediaCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.play_pause()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "play_pause")
        self.assertEqual(result.data["title"], "Song")
        self.assertEqual(result.data["artist"], "Artist")
        self.assertEqual(result.data["app"], "Music")
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(security.intents[0].action, "play_pause")
        self.assertEqual(tools.play_calls, 1)

    def test_next_track_success(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools(
            state={
                "media_available": True,
                "playing": True,
                "title": "New Song",
                "artist": "Artist",
                "app": "Music",
                "command_executed": True,
                "media_observed": True,
                "previous_title": "Old Song",
                "previous_artist": "Artist",
                "track_changed": True,
                "observation_attempts": 2,
                "command_attempts": 1,
            }
        )
        capability = MediaCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.next_track()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "next_track")
        self.assertEqual(result.data["title"], "New Song")
        self.assertTrue(result.data["command_executed"])
        self.assertTrue(result.data["media_observed"])
        self.assertEqual(result.data["previous_title"], "Old Song")
        self.assertTrue(result.data["track_changed"])
        self.assertEqual(result.data["observation_attempts"], 2)
        self.assertEqual(result.data["command_attempts"], 1)
        self.assertEqual(security.intents[0].action, "next_track")
        self.assertEqual(tools.next_calls, 1)

    def test_next_track_without_observed_track_change_uses_prudent_message(self):
        tools = RecordingMacOSTools(
            state={
                "media_available": True,
                "playing": True,
                "title": "Same Song",
                "artist": "Artist",
                "app": "Music",
                "command_executed": True,
                "media_observed": True,
                "previous_title": "Same Song",
                "previous_artist": "Artist",
                "track_changed": False,
                "observation_attempts": 3,
                "command_attempts": 2,
            }
        )
        capability = MediaCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.next_track()

        self.assertTrue(result.ok)
        self.assertFalse(result.data["track_changed"])
        self.assertEqual(result.data["observation_attempts"], 3)
        self.assertEqual(result.data["command_attempts"], 2)
        self.assertIn("aucun changement de piste", result.message)

    def test_previous_track_success(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = MediaCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.previous_track()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "previous_track")
        self.assertEqual(result.data["title"], "Song")
        self.assertEqual(security.intents[0].action, "previous_track")
        self.assertEqual(tools.previous_calls, 1)

    def test_get_media_state_success_does_not_require_security(self):
        security = RecordingSecurity()
        tools = RecordingMacOSTools()
        capability = MediaCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.get_media_state()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "get_media_state")
        self.assertEqual(result.data["playing"], True)
        self.assertEqual(result.data["title"], "Song")
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.state_calls, 1)

    def test_no_compatible_media_active_returns_explicit_result(self):
        tools = RecordingMacOSTools(
            state={
                "media_available": False,
                "playing": False,
                "title": None,
                "artist": None,
                "app": None,
            }
        )
        capability = MediaCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.get_media_state()

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "get_media_state")
        self.assertFalse(result.data["media_available"])
        self.assertIsNone(result.data["title"])
        self.assertIn("Aucun media compatible", result.message)

    def test_system_error_returns_failure(self):
        tools = RecordingMacOSTools(
            play_error=RuntimeError("media failed"),
        )
        capability = MediaCapability(
            security=RecordingSecurity(),
            macos_tools=tools,
        )

        result = capability.play_pause()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")
        self.assertIn("media failed", result.message)

    def test_security_refusal_does_not_call_macos(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingMacOSTools()
        capability = MediaCapability(
            security=security,
            macos_tools=tools,
        )

        result = capability.next_track()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(len(security.intents), 1)
        self.assertEqual(tools.next_calls, 0)

    def test_tool_result_serialization_includes_media_fields(self):
        capability = MediaCapability(
            security=RecordingSecurity(),
            macos_tools=RecordingMacOSTools(),
        )

        result = capability.get_media_state().to_livekit_dict()

        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "get_media_state",
                "media_available": True,
                "playing": True,
                "title": "Song",
                "artist": "Artist",
                "app": "Music",
                "message": "Song de Artist est en cours de lecture dans Music.",
            },
        )


if __name__ == "__main__":
    unittest.main()
