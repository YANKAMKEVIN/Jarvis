import os
import unittest
from datetime import datetime

from jarvis.tools.screenshot import ScreenCaptureError, ScreenCaptureTools


class RecordingRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))

        if not self.responses:
            raise AssertionError("Appel de commande inattendu : file vide.")

        return self.responses.pop(0)


FIXED_CLOCK = datetime(2026, 1, 2, 3, 4, 5, 678901)


def make_tools(responses, prober=None, output_dir="/out"):
    runner = RecordingRunner(responses)
    made_dirs = []
    tools = ScreenCaptureTools(
        runner=runner,
        prober=prober or (lambda _path: {"exists": True, "bytes": 2048}),
        clock=lambda: FIXED_CLOCK,
        dir_maker=made_dirs.append,
        output_dir=output_dir,
    )
    return tools, runner, made_dirs


class ScreenCaptureScreenTest(unittest.TestCase):
    def test_capture_screen_builds_default_path_and_confirms(self):
        tools, runner, made_dirs = make_tools([
            (0, "", ""),  # screencapture
            (0, "pixelWidth: 1440\npixelHeight: 900", ""),  # sips
        ])

        state = tools.capture_screen()

        expected_path = os.path.join(
            "/out", "jarvis-screenshot-20260102-030405-678901.png"
        )
        self.assertEqual(state["path"], expected_path)
        self.assertTrue(state["command_executed"])
        self.assertTrue(state["state_confirmed"])
        self.assertEqual(state["bytes"], 2048)
        self.assertEqual(state["width"], 1440)
        self.assertEqual(state["height"], 900)
        self.assertEqual(
            runner.calls[0],
            ["screencapture", "-x", "-t", "png", expected_path],
        )
        self.assertEqual(made_dirs, ["/out"])

    def test_capture_screen_with_display_adds_flag(self):
        tools, runner, _ = make_tools([
            (0, "", ""),
            (0, "pixelWidth: 10\npixelHeight: 10", ""),
        ])

        tools.capture_screen(display=2)

        self.assertIn("-D", runner.calls[0])
        self.assertIn("2", runner.calls[0])

    def test_capture_screen_rejects_invalid_display(self):
        tools, _, _ = make_tools([])

        with self.assertRaises(ScreenCaptureError) as context:
            tools.capture_screen(display=0)

        self.assertEqual(context.exception.code, "invalid_display")

    def test_capture_failed_when_screencapture_errors(self):
        tools, _, _ = make_tools([(1, "", "cannot capture")])

        with self.assertRaises(ScreenCaptureError) as context:
            tools.capture_screen()

        self.assertEqual(context.exception.code, "capture_failed")

    def test_missing_file_is_not_confirmed_and_skips_dimensions(self):
        tools, runner, _ = make_tools(
            [(0, "", "")],
            prober=lambda _path: {"exists": False, "bytes": 0},
        )

        state = tools.capture_screen()

        self.assertTrue(state["command_executed"])
        self.assertFalse(state["state_confirmed"])
        self.assertIsNone(state["width"])
        self.assertEqual(len(runner.calls), 1)  # no sips call

    def test_dimensions_optional_when_sips_fails(self):
        tools, _, _ = make_tools([
            (0, "", ""),
            (1, "", "sips error"),
        ])

        state = tools.capture_screen()

        self.assertTrue(state["state_confirmed"])
        self.assertIsNone(state["width"])
        self.assertIsNone(state["height"])


class ScreenCaptureRegionTest(unittest.TestCase):
    def test_capture_region_builds_rect_flag(self):
        tools, runner, _ = make_tools([
            (0, "", ""),
            (0, "pixelWidth: 30\npixelHeight: 40", ""),
        ])

        state = tools.capture_region(10, 20, 30, 40)

        self.assertEqual(state["region"], {"x": 10, "y": 20, "width": 30, "height": 40})
        self.assertIn("-R", runner.calls[0])
        self.assertIn("10,20,30,40", runner.calls[0])

    def test_capture_region_rejects_non_positive_size(self):
        tools, _, _ = make_tools([])

        with self.assertRaises(ScreenCaptureError) as context:
            tools.capture_region(0, 0, 0, 100)

        self.assertEqual(context.exception.code, "invalid_region")

    def test_capture_region_rejects_negative_origin(self):
        tools, _, _ = make_tools([])

        with self.assertRaises(ScreenCaptureError) as context:
            tools.capture_region(-1, 0, 10, 10)

        self.assertEqual(context.exception.code, "invalid_region")

    def test_capture_region_rejects_non_integer(self):
        tools, _, _ = make_tools([])

        with self.assertRaises(ScreenCaptureError) as context:
            tools.capture_region("a", 0, 10, 10)

        self.assertEqual(context.exception.code, "invalid_region")


class ScreenCapturePathTest(unittest.TestCase):
    def test_relative_path_joins_output_dir_and_adds_png(self):
        tools, runner, _ = make_tools([
            (0, "", ""),
            (0, "pixelWidth: 1\npixelHeight: 1", ""),
        ])

        state = tools.capture_screen(path="shot")

        self.assertEqual(state["path"], os.path.join("/out", "shot.png"))

    def test_absolute_path_is_respected(self):
        tools, _, _ = make_tools([
            (0, "", ""),
            (0, "pixelWidth: 1\npixelHeight: 1", ""),
        ])

        state = tools.capture_screen(path="/tmp/custom.png")

        self.assertEqual(state["path"], "/tmp/custom.png")

    def test_blank_path_is_rejected(self):
        tools, _, _ = make_tools([])

        with self.assertRaises(ScreenCaptureError) as context:
            tools.capture_screen(path="   ")

        self.assertEqual(context.exception.code, "invalid_path")


if __name__ == "__main__":
    unittest.main()
