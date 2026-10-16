import unittest

from jarvis.capabilities.shortcuts import ShortcutsCapability
from jarvis.tools.shortcuts import ShortcutsError, ShortcutsTools


def runner_ok(stdout):
    return lambda argv: (0, stdout, "")


def runner_fail(stderr="", code=1):
    return lambda argv: (code, "", stderr)


class ShortcutsToolsTests(unittest.TestCase):
    def test_list(self):
        tools = ShortcutsTools(runner=runner_ok("Focus travail\nNe pas deranger\n"))
        self.assertEqual(tools.list_shortcuts(), ["Focus travail", "Ne pas deranger"])

    def test_run_calls_cli(self):
        captured = {}

        def runner(argv):
            captured["argv"] = argv
            return (0, "", "")

        ShortcutsTools(runner=runner).run_shortcut("Focus")
        self.assertEqual(captured["argv"], ["shortcuts", "run", "Focus"])

    def test_run_unknown_raises(self):
        with self.assertRaises(ShortcutsError) as ctx:
            ShortcutsTools(runner=runner_fail("not found")).run_shortcut("Absent")
        self.assertEqual(ctx.exception.code, "shortcut_failed")

    def test_run_blank_name(self):
        with self.assertRaises(ShortcutsError) as ctx:
            ShortcutsTools(runner=runner_ok("")).run_shortcut("  ")
        self.assertEqual(ctx.exception.code, "invalid_name")

    def test_cli_unavailable(self):
        tools = ShortcutsTools(runner=lambda argv: (127, "", "__no_cli__"))
        with self.assertRaises(ShortcutsError) as ctx:
            tools.list_shortcuts()
        self.assertEqual(ctx.exception.code, "shortcuts_unavailable")


class ShortcutsCapabilityTests(unittest.TestCase):
    def test_list_ok(self):
        cap = ShortcutsCapability(ShortcutsTools(runner=runner_ok("A\nB\n")))
        result = cap.list_shortcuts()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 2)

    def test_run_ok(self):
        cap = ShortcutsCapability(ShortcutsTools(runner=runner_ok("")))
        result = cap.run_shortcut("Focus")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["shortcut"], "Focus")

    def test_run_failure_surfaced(self):
        cap = ShortcutsCapability(ShortcutsTools(runner=runner_fail("nope")))
        result = cap.run_shortcut("Absent")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "shortcut_failed")


if __name__ == "__main__":
    unittest.main()
