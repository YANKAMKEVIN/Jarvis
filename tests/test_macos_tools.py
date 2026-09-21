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


if __name__ == "__main__":
    unittest.main()
