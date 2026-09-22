import unittest
from unittest.mock import patch

from jarvis.tools.macos import MacOSTools


class FakeCompletedProcess:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class MacOSToolsTest(unittest.TestCase):
    def test_get_volume_reads_output_volume_without_real_macos_call(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="42\n"),
        ) as run:
            volume = MacOSTools().get_volume()

        self.assertEqual(volume, 42)
        run.assert_called_once_with(
            [
                "osascript",
                "-e",
                "output volume of (get volume settings)",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_open_app_uses_open_with_argument_list_for_names_with_spaces(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(),
        ) as run:
            message = MacOSTools().open_app("Visual Studio Code")

        self.assertEqual(message, "Visual Studio Code a ete ouvert.")
        run.assert_called_once_with(
            ["open", "-a", "Visual Studio Code"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_open_app_raises_when_macos_returns_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                returncode=1,
                stderr="Application introuvable",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Application introuvable"):
                MacOSTools().open_app("Missing App")

    def test_close_app_uses_osascript_with_escaped_name(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(),
        ) as run:
            message = MacOSTools().close_app("Google Chrome")

        self.assertEqual(message, "Google Chrome a ete ferme.")
        run.assert_called_once_with(
            [
                "osascript",
                "-e",
                'tell application "Google Chrome" to quit',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_close_app_raises_when_macos_returns_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                returncode=1,
                stderr="Quit failed",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Quit failed"):
                MacOSTools().close_app("Spotify")

    def test_is_app_running_reads_boolean_without_real_macos_call(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="true\n"),
        ) as run:
            running = MacOSTools().is_app_running("Visual Studio Code")

        self.assertTrue(running)
        run.assert_called_once_with(
            [
                "osascript",
                "-e",
                'application "Visual Studio Code" is running',
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_is_app_running_returns_false_for_false_output(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="false\n"),
        ):
            running = MacOSTools().is_app_running("Spotify")

        self.assertFalse(running)

    def test_is_app_running_raises_when_macos_returns_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(
                returncode=1,
                stderr="State check failed",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "State check failed"):
                MacOSTools().is_app_running("Spotify")

    def test_get_media_state_reads_music_metadata_without_real_macos_call(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="playing\nSong\nArtist\n"),
        ) as run:
            state = MacOSTools().get_media_state("Music")

        self.assertEqual(
            state,
            {
                "media_available": True,
                "playing": True,
                "title": "Song",
                "artist": "Artist",
                "app": "Music",
            },
        )
        args = run.call_args.args[0]
        self.assertEqual(args[0:2], ["osascript", "-e"])
        self.assertIn('tell application "Music"', args[2])
        self.assertIn("player state as text", args[2])

    def test_get_media_state_returns_no_media_when_no_supported_app_is_running(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="false\n"),
        ):
            state = MacOSTools().get_media_state()

        self.assertEqual(
            state,
            {
                "media_available": False,
                "playing": False,
                "title": None,
                "artist": None,
                "app": None,
            },
        )

    def test_play_pause_uses_active_supported_media_app_and_confirms_state(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="paused\nSong\nArtist\n"),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout="playing\nSong\nArtist\n"),
            ],
        ) as run:
            state = MacOSTools().play_pause()

        self.assertTrue(state["playing"])
        self.assertEqual(state["title"], "Song")
        self.assertEqual(state["app"], "Music")
        self.assertIn('application "Music" is running', run.call_args_list[0].args[0][2])
        self.assertIn('tell application "Music"', run.call_args_list[2].args[0][2])
        self.assertIn("playpause", run.call_args_list[2].args[0][2])

    def test_next_track_uses_active_supported_media_app(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="playing\nOld Song\nArtist\n"),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout="playing\nNew Song\nArtist\n"),
            ],
        ) as run:
            state = MacOSTools().next_track()

        self.assertEqual(state["title"], "New Song")
        self.assertTrue(state["command_executed"])
        self.assertTrue(state["media_observed"])
        self.assertEqual(state["previous_title"], "Old Song")
        self.assertEqual(state["previous_artist"], "Artist")
        self.assertTrue(state["track_changed"])
        self.assertEqual(state["observation_attempts"], 1)
        self.assertEqual(state["command_attempts"], 1)
        self.assertIn("next track", run.call_args_list[2].args[0][2])

    def test_next_track_reports_no_observed_track_change_without_retry(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                ],
            ) as run:
                state = MacOSTools().next_track()

        self.assertEqual(state["title"], "Same Song")
        self.assertEqual(state["previous_title"], "Same Song")
        self.assertFalse(state["track_changed"])
        self.assertEqual(state["observation_attempts"], 3)
        self.assertEqual(state["command_attempts"], 1)
        self.assertEqual(run.call_count, 6)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(
            sum(
                "next track" in call.args[0][2]
                for call in run.call_args_list
            ),
            1,
        )

    def test_next_track_observes_delayed_metadata_change_with_bounded_check(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nOld Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nOld Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nNew Song\nArtist\n"),
                ],
            ) as run:
                state = MacOSTools().next_track()

        self.assertTrue(state["track_changed"])
        self.assertEqual(state["title"], "New Song")
        self.assertEqual(state["previous_title"], "Old Song")
        self.assertEqual(state["observation_attempts"], 2)
        self.assertEqual(state["command_attempts"], 1)
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(
            sum(
                "next track" in call.args[0][2]
                for call in run.call_args_list
            ),
            1,
        )

    def test_previous_track_uses_active_supported_media_app(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                FakeCompletedProcess(stdout=""),
                FakeCompletedProcess(stdout="playing\nPrevious Song\nArtist\n"),
            ],
        ) as run:
            state = MacOSTools().previous_track()

        self.assertEqual(state["title"], "Previous Song")
        self.assertTrue(state["track_changed"])
        self.assertEqual(state["command_attempts"], 1)
        self.assertIn("previous track", run.call_args_list[2].args[0][2])

    def test_previous_track_sends_second_command_when_first_does_not_change_track(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nPrevious Song\nArtist\n"),
                ],
            ) as run:
                state = MacOSTools().previous_track()

        self.assertTrue(state["track_changed"])
        self.assertEqual(state["title"], "Previous Song")
        self.assertEqual(state["previous_title"], "Current Song")
        self.assertEqual(state["command_attempts"], 2)
        self.assertEqual(state["observation_attempts"], 1)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(
            sum(
                "previous track" in call.args[0][2]
                for call in run.call_args_list
            ),
            2,
        )

    def test_previous_track_sends_at_most_two_commands_when_track_stays_same(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                    FakeCompletedProcess(stdout="playing\nSame Song\nArtist\n"),
                ],
            ) as run:
                state = MacOSTools().previous_track()

        self.assertFalse(state["track_changed"])
        self.assertEqual(state["observation_attempts"], 3)
        self.assertEqual(state["command_attempts"], 2)
        self.assertEqual(sleep.call_count, 4)
        self.assertEqual(
            sum(
                "previous track" in call.args[0][2]
                for call in run.call_args_list
            ),
            2,
        )

    def test_previous_track_does_not_send_second_command_when_media_disappears(self):
        with patch("jarvis.tools.macos.time.sleep") as sleep:
            with patch(
                "jarvis.tools.macos.subprocess.run",
                side_effect=[
                    FakeCompletedProcess(stdout="true\n"),
                    FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                    FakeCompletedProcess(stdout=""),
                    FakeCompletedProcess(stdout="\n\n\n"),
                ],
            ) as run:
                state = MacOSTools().previous_track()

        self.assertFalse(state["media_observed"])
        self.assertFalse(state["track_changed"])
        self.assertEqual(state["command_attempts"], 1)
        self.assertEqual(sleep.call_count, 0)
        self.assertEqual(
            sum(
                "previous track" in call.args[0][2]
                for call in run.call_args_list
            ),
            1,
        )

    def test_previous_track_does_not_send_second_command_after_system_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="playing\nCurrent Song\nArtist\n"),
                FakeCompletedProcess(returncode=1, stderr="previous failed"),
            ],
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "previous failed"):
                MacOSTools().previous_track()

        self.assertEqual(
            sum(
                "previous track" in call.args[0][2]
                for call in run.call_args_list
            ),
            1,
        )

    def test_media_action_raises_when_no_supported_app_is_active(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            return_value=FakeCompletedProcess(stdout="false\n"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Aucune application media"):
                MacOSTools().next_track()

    def test_media_action_raises_when_macos_returns_error(self):
        with patch(
            "jarvis.tools.macos.subprocess.run",
            side_effect=[
                FakeCompletedProcess(stdout="true\n"),
                FakeCompletedProcess(stdout="playing\nSong\nArtist\n"),
                FakeCompletedProcess(returncode=1, stderr="media command failed"),
            ],
        ):
            with self.assertRaisesRegex(RuntimeError, "media command failed"):
                MacOSTools().play_pause()


if __name__ == "__main__":
    unittest.main()
