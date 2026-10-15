import unittest

from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.vision import VisionCapability
from jarvis.tools.vision import VisionError


def capture_ok(action="capture_window", **data):
    base = {
        "path": "/Users/x/Pictures/Jarvis/shot.png",
        "bytes": 1234,
        "width": 3024,
        "height": 1964,
        "command_executed": True,
        "state_confirmed": True,
        "target_app": "Safari",
    }
    base.update(data)
    return ToolResult.success(action=action, message="capture ok", **base)


class FakeScreenshot:
    def __init__(self, screen=None, window=None):
        self.screen = screen or capture_ok("capture_screen", target_app=None)
        self.window = window or capture_ok("capture_window")
        self.calls = []

    def capture_screen(self, path=None, display=None):
        self.calls.append(("capture_screen",))
        return self.screen

    def capture_window(self, app_name=None, path=None):
        self.calls.append(("capture_window", app_name))
        return self.window


class FakeVisionTools:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "analysis": "Une page web est affichee.",
            "model": "gemini-2.5-flash",
            "image_bytes": 1234,
            "mime_type": "image/png",
            "duration_ms": 42,
        }
        self.error = error
        self.calls = []

    def analyze(self, image_path, prompt):
        self.calls.append((image_path, prompt))
        if self.error is not None:
            raise self.error
        return dict(self.result)


class VisionCapabilityTest(unittest.TestCase):
    def test_describe_window_captures_then_analyzes(self):
        shot = FakeScreenshot()
        vision = FakeVisionTools()
        capability = VisionCapability(screenshot=shot, vision_tools=vision)

        result = capability.describe_screen()

        self.assertTrue(result.ok)
        self.assertEqual(result.data["analysis"], "Une page web est affichee.")
        self.assertEqual(result.data["source"], "window")
        self.assertEqual(result.data["model"], "gemini-2.5-flash")
        self.assertEqual(result.data["image_width"], 3024)
        self.assertEqual(shot.calls, [("capture_window", None)])
        self.assertEqual(vision.calls[0][0], "/Users/x/Pictures/Jarvis/shot.png")

    def test_describe_screen_uses_full_screen_capture(self):
        shot = FakeScreenshot()
        capability = VisionCapability(screenshot=shot, vision_tools=FakeVisionTools())

        result = capability.describe_screen(target="screen")

        self.assertTrue(result.ok)
        self.assertEqual(shot.calls, [("capture_screen",)])

    def test_target_aliases_map_to_real_targets(self):
        for alias, expected_call in (
            ("active_window", ("capture_window", None)),
            ("fenêtre", ("capture_window", None)),
            ("ecran", ("capture_screen",)),
            ("tout l'écran", ("capture_screen",)),
        ):
            with self.subTest(alias=alias):
                shot = FakeScreenshot()
                capability = VisionCapability(
                    screenshot=shot, vision_tools=FakeVisionTools()
                )

                result = capability.describe_screen(target=alias)

                self.assertTrue(result.ok)
                self.assertEqual(shot.calls, [expected_call])

    def test_invalid_target_does_not_capture(self):
        shot = FakeScreenshot()
        vision = FakeVisionTools()
        capability = VisionCapability(screenshot=shot, vision_tools=vision)

        result = capability.describe_screen(target="webcam")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_target")
        self.assertEqual(shot.calls, [])
        self.assertEqual(vision.calls, [])

    def test_capture_failure_skips_analysis(self):
        shot = FakeScreenshot(window=ToolResult.failure(
            action="capture_window", message="echec", error_code="capture_failed",
        ))
        vision = FakeVisionTools()
        capability = VisionCapability(screenshot=shot, vision_tools=vision)

        result = capability.describe_screen()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "capture_failed")
        self.assertEqual(vision.calls, [])

    def test_unconfirmed_capture_skips_analysis(self):
        shot = FakeScreenshot(window=capture_ok(state_confirmed=False))
        vision = FakeVisionTools()
        capability = VisionCapability(screenshot=shot, vision_tools=vision)

        result = capability.describe_screen()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "capture_not_confirmed")
        self.assertEqual(vision.calls, [])

    def test_ask_about_screen_requires_question(self):
        shot = FakeScreenshot()
        vision = FakeVisionTools()
        capability = VisionCapability(screenshot=shot, vision_tools=vision)

        result = capability.ask_about_screen("   ")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_question")
        self.assertEqual(shot.calls, [])

    def test_ask_about_screen_embeds_question_and_reports_length(self):
        shot = FakeScreenshot()
        vision = FakeVisionTools()
        capability = VisionCapability(screenshot=shot, vision_tools=vision)

        result = capability.ask_about_screen("Quelle temperature est affichee ?")

        self.assertTrue(result.ok)
        self.assertEqual(
            result.data["question_length"], len("Quelle temperature est affichee ?")
        )
        self.assertIn("Quelle temperature", vision.calls[0][1])

    def test_vision_error_propagates(self):
        shot = FakeScreenshot()
        vision = FakeVisionTools(
            error=VisionError("trop lourde", code="image_too_large")
        )
        capability = VisionCapability(screenshot=shot, vision_tools=vision)

        result = capability.describe_screen()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "image_too_large")

    def test_output_never_contains_coordinates(self):
        shot = FakeScreenshot()
        capability = VisionCapability(screenshot=shot, vision_tools=FakeVisionTools())

        result = capability.describe_screen()

        forbidden = {"x", "y", "coordinate", "coordinates", "position", "point"}
        self.assertTrue(forbidden.isdisjoint(result.data.keys()))


if __name__ == "__main__":
    unittest.main()
