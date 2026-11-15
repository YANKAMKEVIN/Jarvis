"""open_file through the live registry: scripts go through confirm_action."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from jarvis.live.registry import create_live_registry
from jarvis.security import SecurityDecision
from jarvis.tools.filesystem import FileSystemTools, PathResolver


class AllowAllSecurity:
    def evaluate(self, intent):
        return SecurityDecision(
            allowed=True, requires_confirmation=False, reason="test security"
        )


class OpenScriptConfirmationTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tempdir.name).resolve()
        (self.home / "Downloads").mkdir()
        registry = create_live_registry(
            security=AllowAllSecurity(),
            filesystem_tools=FileSystemTools(resolver=PathResolver(home=self.home)),
            # Hardware-backed tools are unavailable off macOS; they are unused here.
            macos_tools=MagicMock(),
            mouse_tools=MagicMock(),
            keyboard_tools=MagicMock(),
            clipboard_tools=MagicMock(),
            accessibility_tools=MagicMock(),
        )
        self.tools = {tool.info.name: tool for tool in registry.livekit_tools()}

    def tearDown(self):
        self.tempdir.cleanup()

    def write(self, name, mode=None):
        path = self.home / "Downloads" / name
        path.write_text("print('hi')\n", encoding="utf-8")
        if mode is not None:
            path.chmod(mode)
        return path

    def test_script_returns_confirmation_request_then_opens_after_confirm(self):
        script = self.write("tool.py")
        completed = Mock(returncode=0, stderr="", stdout="")

        with patch(
            "jarvis.tools.filesystem.subprocess.run", return_value=completed
        ) as run:
            prepared = asyncio.run(self.tools["open_file"](str(script)))
            run.assert_not_called()

            self.assertTrue(prepared["ok"])
            self.assertTrue(prepared["requires_confirmation"])
            self.assertTrue(prepared["token"])

            confirmed = asyncio.run(self.tools["confirm_action"](prepared["token"]))

        self.assertTrue(confirmed["ok"])
        self.assertEqual(confirmed["action"], "open_file")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["open", str(script)])
        self.assertIn("timeout", run.call_args.kwargs)

    def test_cancelled_script_is_never_opened(self):
        script = self.write("tool.rb")

        with patch("jarvis.tools.filesystem.subprocess.run") as run:
            prepared = asyncio.run(self.tools["open_file"](str(script)))
            asyncio.run(self.tools["cancel_action"](prepared["token"]))
            again = asyncio.run(self.tools["confirm_action"](prepared["token"]))

        self.assertEqual(again["error_code"], "no_pending_action")
        run.assert_not_called()

    def test_real_executable_is_still_refused_without_token(self):
        command = self.write("run.command")
        bare = self.write("payload", mode=0o755)

        with patch("jarvis.tools.filesystem.subprocess.run") as run:
            for path in (command, bare):
                result = asyncio.run(self.tools["open_file"](str(path)))
                self.assertFalse(result["ok"])
                self.assertEqual(result["error_code"], "executable_refused")
                self.assertNotIn("token", result)

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
