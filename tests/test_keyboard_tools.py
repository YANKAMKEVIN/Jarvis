import subprocess
import unittest

from jarvis.tools.keyboard import (
    KeyboardError,
    KeyboardTools,
    MAX_TYPE_TEXT_CHARS,
)


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


class KeyboardToolsTest(unittest.TestCase):
    def make_tools(self, *responses):
        return KeyboardTools(
            runner=RecordingRunner([
                completed(stdout="Safari\nExample\n"),
                *responses,
            ])
        )

    def assert_no_shell(self, runner):
        for _args, kwargs in runner.calls:
            self.assertFalse(kwargs.get("shell", False))

    def test_type_text_ascii(self):
        tools = self.make_tools(completed())

        result = tools.type_text("Bonjour")

        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(result["length"], 7)
        self.assertEqual(result["target_app"], "Safari")
        script = tools.runner.calls[1][0][2]
        self.assertIn('keystroke "Bonjour"', script)
        self.assert_no_shell(tools.runner)

    def test_type_text_accents_apostrophes_unicode_and_emoji(self):
        text = "été Noël l'apostrophe café 😀"
        tools = self.make_tools(completed())

        result = tools.type_text(text)

        self.assertEqual(result["length"], len(text))
        script = tools.runner.calls[1][0][2]
        self.assertIn(text, script)

    def test_type_text_escapes_applescript_string(self):
        tools = self.make_tools(completed())

        tools.type_text('Bonjour "Jarvis" \\ test')

        script = tools.runner.calls[1][0][2]
        self.assertIn('\\"Jarvis\\"', script)
        self.assertIn("\\\\ test", script)

    def test_type_text_multiline_uses_enter_between_segments(self):
        tools = self.make_tools(completed())

        result = tools.type_text("Bonjour\nJarvis")

        self.assertEqual(result["line_count"], 2)
        script = tools.runner.calls[1][0][2]
        self.assertIn('keystroke "Bonjour"', script)
        self.assertIn("key code 36", script)
        self.assertIn('keystroke "Jarvis"', script)

    def test_type_text_rejects_empty_text(self):
        tools = KeyboardTools(runner=RecordingRunner([]))

        with self.assertRaises(KeyboardError) as context:
            tools.type_text("")

        self.assertEqual(context.exception.code, "empty_text")
        self.assertEqual(tools.runner.calls, [])

    def test_type_text_rejects_too_long_text(self):
        tools = KeyboardTools(runner=RecordingRunner([]))

        with self.assertRaises(KeyboardError) as context:
            tools.type_text("a" * (MAX_TYPE_TEXT_CHARS + 1))

        self.assertEqual(context.exception.code, "text_too_long")
        self.assertEqual(context.exception.data["max_length"], MAX_TYPE_TEXT_CHARS)
        self.assertEqual(tools.runner.calls, [])

    def test_press_allowed_keys(self):
        expected_codes = {
            "enter": 36,
            "escape": 53,
            "tab": 48,
            "space": 49,
            "arrow_up": 126,
            "arrow_down": 125,
            "arrow_left": 123,
            "arrow_right": 124,
        }

        for key, code in expected_codes.items():
            with self.subTest(key=key):
                tools = self.make_tools(completed())

                result = tools.press_key(key)

                self.assertEqual(result["key"], key)
                self.assertFalse(result["state_confirmed"])
                self.assertIn(f"key code {code}", tools.runner.calls[1][0][2])

    def test_press_key_accepts_aliases(self):
        tools = self.make_tools(completed())

        result = tools.press_key(" Échap ")

        self.assertEqual(result["key"], "escape")

    def test_press_key_rejects_delete_and_backspace(self):
        for key in ("delete", "backspace"):
            with self.subTest(key=key):
                tools = KeyboardTools(runner=RecordingRunner([]))

                with self.assertRaises(KeyboardError) as context:
                    tools.press_key(key)

                self.assertEqual(context.exception.code, "keyboard_key_not_allowed")
                self.assertEqual(tools.runner.calls, [])

    def test_press_key_rejects_unknown_key(self):
        tools = KeyboardTools(runner=RecordingRunner([]))

        with self.assertRaises(KeyboardError) as context:
            tools.press_key("f13")

        self.assertEqual(context.exception.code, "unknown_key")
        self.assertEqual(tools.runner.calls, [])

    def test_delete_backward_sends_backspace_key_code(self):
        tools = self.make_tools(completed())

        result = tools.delete_backward()

        self.assertTrue(result["command_executed"])
        self.assertFalse(result["state_confirmed"])
        self.assertEqual(result["key"], "backspace")
        script = tools.runner.calls[1][0][2]
        self.assertIn("key code 51", script)
        self.assert_no_shell(tools.runner)

    def test_allowed_hotkeys(self):
        cases = [
            (["cmd", "a"], ("command", "a")),
            (["commande", "c"], ("command", "c")),
            (["command", "v"], ("command", "v")),
            (["command", "z"], ("command", "z")),
            (["cmd", "shift", "z"], ("command", "shift", "z")),
            (["command", "f"], ("command", "f")),
            (["command", "s"], ("command", "s")),
        ]

        for keys, normalized in cases:
            with self.subTest(keys=keys):
                tools = self.make_tools(completed())

                result = tools.hotkey(keys)

                self.assertEqual(result["keys"], list(normalized))
                script = tools.runner.calls[1][0][2]
                self.assertIn(f'keystroke "{normalized[-1]}"', script)
                self.assertIn("command down", script)

    def test_compact_hotkeys_are_normalized_and_allowed(self):
        cases = [
            (["command+a"], ("command", "a")),
            (["command+c"], ("command", "c")),
            (["command+shift+z"], ("command", "shift", "z")),
        ]

        for keys, normalized in cases:
            with self.subTest(keys=keys):
                tools = self.make_tools(completed())

                result = tools.hotkey(keys)

                self.assertEqual(result["keys"], list(normalized))
                action_scripts = [
                    call[0][2]
                    for call in tools.runner.calls
                    if "keystroke" in call[0][2]
                ]
                self.assertEqual(len(action_scripts), 1)
                self.assertIn(f'keystroke "{normalized[-1]}"', action_scripts[0])

    def test_hotkey_refuses_dangerous_or_unknown_combinations(self):
        cases = [
            (["command", "q"], "hotkey_not_allowed"),
            (["command", "w"], "hotkey_not_allowed"),
            (["command", "enter"], "hotkey_not_allowed"),
            (["option", "command", "escape"], "hotkey_not_allowed"),
            (["command", "delete"], "hotkey_not_allowed"),
        ]

        for keys, code in cases:
            with self.subTest(keys=keys):
                tools = KeyboardTools(runner=RecordingRunner([]))

                with self.assertRaises(KeyboardError) as context:
                    tools.hotkey(keys)

                self.assertEqual(context.exception.code, code)
                self.assertEqual(tools.runner.calls, [])

    def test_compact_hotkey_refuses_dangerous_combinations(self):
        cases = [
            ["command+q"],
            ["command+w"],
            ["command+delete"],
            ["command+enter"],
            ["option+command+escape"],
        ]

        for keys in cases:
            with self.subTest(keys=keys):
                tools = KeyboardTools(runner=RecordingRunner([]))

                with self.assertRaises(KeyboardError) as context:
                    tools.hotkey(keys)

                self.assertEqual(context.exception.code, "hotkey_not_allowed")
                self.assertEqual(tools.runner.calls, [])

    def test_hotkey_refuses_unknown_modifier(self):
        tools = KeyboardTools(runner=RecordingRunner([]))

        with self.assertRaises(KeyboardError) as context:
            tools.hotkey(["hyper", "a"])

        self.assertEqual(context.exception.code, "unknown_modifier_or_key")
        self.assertEqual(tools.runner.calls, [])

    def test_hotkey_refuses_duplicate_modifier(self):
        tools = KeyboardTools(runner=RecordingRunner([]))

        with self.assertRaises(KeyboardError) as context:
            tools.hotkey(["cmd", "command", "a"])

        self.assertEqual(context.exception.code, "duplicate_modifier")
        self.assertEqual(tools.runner.calls, [])

    def test_accessibility_permission_error_is_structured(self):
        tools = self.make_tools(
            completed(stderr="osascript is not authorized for accessibility", returncode=1),
        )

        with self.assertRaises(KeyboardError) as context:
            tools.press_key("enter")

        self.assertEqual(context.exception.code, "accessibility_permission_error")

    def test_subprocess_error_is_structured(self):
        tools = self.make_tools(completed(stderr="boom", returncode=1))

        with self.assertRaises(KeyboardError) as context:
            tools.press_key("enter")

        self.assertEqual(context.exception.code, "system_error")

    def test_context_read_failure_does_not_block_command(self):
        runner = RecordingRunner([
            completed(stderr="context failed", returncode=1),
            completed(),
        ])
        tools = KeyboardTools(runner=runner)

        result = tools.press_key("enter")

        self.assertTrue(result["command_executed"])
        self.assertIsNone(result["target_app"])
        self.assertEqual(result["target_context_error_code"], "system_error")


if __name__ == "__main__":
    unittest.main()
