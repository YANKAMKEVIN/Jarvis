import subprocess
import unittest

from jarvis.tools.clipboard import ClipboardError, ClipboardTools, MAX_RETURN_CHARS


class RecordingRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))

        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class ClipboardToolsTest(unittest.TestCase):
    def test_get_text_normal(self):
        runner = RecordingRunner([completed(stdout="Bonjour")])
        tools = ClipboardTools(runner=runner)

        result = tools.get_text()

        self.assertEqual(result["text"], "Bonjour")
        self.assertTrue(result["has_text"])
        self.assertEqual(result["length"], 7)
        self.assertEqual(result["returned_length"], 7)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["content_type"], "text")
        self.assertEqual(
            runner.calls[0][0],
            ["/usr/bin/pbpaste", "-Prefer", "txt"],
        )

    def test_get_text_no_text_detected(self):
        runner = RecordingRunner([completed(stdout="")])
        tools = ClipboardTools(runner=runner)

        result = tools.get_text()

        self.assertFalse(result["has_text"])
        self.assertIsNone(result["text"])
        self.assertEqual(result["length"], 0)
        self.assertEqual(result["content_type"], "no_text_detected")

    def test_get_text_unicode_and_multiline(self):
        text = "Bonjour Estelle\nCafe creme ☕️"
        runner = RecordingRunner([completed(stdout=text)])
        tools = ClipboardTools(runner=runner)

        result = tools.get_text()

        self.assertEqual(result["text"], text)
        self.assertEqual(result["length"], len(text))

    def test_get_text_long_text_is_truncated_for_return(self):
        text = "a" * (MAX_RETURN_CHARS + 10)
        runner = RecordingRunner([completed(stdout=text)])
        tools = ClipboardTools(runner=runner)

        result = tools.get_text()

        self.assertTrue(result["has_text"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["length"], MAX_RETURN_CHARS + 10)
        self.assertEqual(result["returned_length"], MAX_RETURN_CHARS)
        self.assertEqual(result["text"], "a" * MAX_RETURN_CHARS)

    def test_get_text_pbpaste_error(self):
        runner = RecordingRunner([completed(stderr="pbpaste failed", returncode=1)])
        tools = ClipboardTools(runner=runner)

        with self.assertRaises(ClipboardError) as context:
            tools.get_text()

        self.assertEqual(context.exception.code, "clipboard_read_error")
        self.assertIn("pbpaste failed", context.exception.message)

    def test_set_text_writes_then_reads_exact_match(self):
        runner = RecordingRunner([
            completed(),
            completed(stdout="Bonjour"),
        ])
        tools = ClipboardTools(runner=runner)

        result = tools.set_text("Bonjour")

        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(result["length"], 7)
        self.assertEqual(runner.calls[0][0], ["/usr/bin/pbcopy"])
        self.assertEqual(runner.calls[0][1]["input"], "Bonjour")
        self.assertEqual(
            runner.calls[1][0],
            ["/usr/bin/pbpaste", "-Prefer", "txt"],
        )

    def test_set_text_long_value_confirms_against_full_raw_clipboard(self):
        text = "b" * (MAX_RETURN_CHARS + 25)
        runner = RecordingRunner([
            completed(),
            completed(stdout=text),
        ])
        tools = ClipboardTools(runner=runner)

        result = tools.set_text(text)

        self.assertTrue(result["state_confirmed"])
        self.assertEqual(result["length"], MAX_RETURN_CHARS + 25)
        self.assertNotIn("text", result)

    def test_set_text_command_succeeds_but_readback_differs(self):
        runner = RecordingRunner([
            completed(),
            completed(stdout="different"),
        ])
        tools = ClipboardTools(runner=runner)

        result = tools.set_text("expected")

        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])

    def test_set_text_pbcopy_error(self):
        runner = RecordingRunner([completed(stderr="pbcopy failed", returncode=1)])
        tools = ClipboardTools(runner=runner)

        with self.assertRaises(ClipboardError) as context:
            tools.set_text("Bonjour")

        self.assertEqual(context.exception.code, "clipboard_write_error")
        self.assertIn("pbcopy failed", context.exception.message)

    def test_set_text_readback_error_does_not_confirm_state(self):
        runner = RecordingRunner([
            completed(),
            completed(stderr="pbpaste failed", returncode=1),
        ])
        tools = ClipboardTools(runner=runner)

        result = tools.set_text("Bonjour")

        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(result["verification_error_code"], "clipboard_read_error")

    def test_clear_confirmed(self):
        runner = RecordingRunner([
            completed(),
            completed(stdout=""),
        ])
        tools = ClipboardTools(runner=runner)

        result = tools.clear()

        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertFalse(result["has_text"])
        self.assertEqual(result["content_type"], "no_text_detected")
        self.assertEqual(runner.calls[0][1]["input"], "")

    def test_clear_not_confirmed_when_text_remains(self):
        runner = RecordingRunner([
            completed(),
            completed(stdout="still here"),
        ])
        tools = ClipboardTools(runner=runner)

        result = tools.clear()

        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertTrue(result["has_text"])
        self.assertEqual(result["length"], len("still here"))

    def test_invalid_set_text_type(self):
        tools = ClipboardTools(runner=RecordingRunner([]))

        with self.assertRaises(ClipboardError) as context:
            tools.set_text(123)

        self.assertEqual(context.exception.code, "invalid_clipboard_text")

    def test_missing_commands_are_explicit(self):
        paste_tools = ClipboardTools(runner=RecordingRunner([FileNotFoundError()]))
        copy_tools = ClipboardTools(runner=RecordingRunner([FileNotFoundError()]))

        with self.assertRaises(ClipboardError) as paste:
            paste_tools.get_text()

        with self.assertRaises(ClipboardError) as copy:
            copy_tools.set_text("Bonjour")

        self.assertEqual(paste.exception.code, "pbpaste_missing")
        self.assertEqual(copy.exception.code, "pbcopy_missing")


if __name__ == "__main__":
    unittest.main()
