import unittest
from unittest.mock import patch

from jarvis.tools.macos import MacOSTools


class FakeCompletedProcess:
    def __init__(self, stdout=""):
        self.stdout = stdout


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


if __name__ == "__main__":
    unittest.main()
