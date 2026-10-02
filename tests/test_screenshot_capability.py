import unittest

from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.screenshot import ScreenshotCapability
from jarvis.tools.screenshot import ScreenCaptureError


class FakeScreenTools:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "path": "/out/shot.png",
            "bytes": 2048,
            "width": 100,
            "height": 50,
            "command_executed": True,
            "state_confirmed": True,
        }
        self.error = error
        self.calls = []

    def capture_screen(self, path=None, display=None):
        self.calls.append(("capture_screen", path, display))

        if self.error is not None:
            raise self.error

        return dict(self.result)

    def capture_region(self, x, y, width, height, path=None):
        self.calls.append(("capture_region", x, y, width, height, path))

        if self.error is not None:
            raise self.error

        state = dict(self.result)
        state["region"] = {"x": x, "y": y, "width": width, "height": height}
        return state


class FakeWindows:
    def __init__(self, focus=None, active=None):
        self.focus = focus
        self.active = active
        self.calls = []

    def focus_window(self, app_name):
        self.calls.append(("focus_window", app_name))
        return self.focus

    def get_active_window(self):
        self.calls.append(("get_active_window",))
        return self.active


def active_window_result(target_app="Safari", x=5, y=10, width=800, height=600):
    return ToolResult.success(
        action="get_active_window",
        message="Fenetre active.",
        target_app=target_app,
        window_title="Une fenetre",
        position={"x": x, "y": y},
        size={"width": width, "height": height},
    )


class ScreenshotScreenTest(unittest.TestCase):
    def test_capture_screen_success(self):
        tools = FakeScreenTools()
        capability = ScreenshotCapability(screen_tools=tools, windows=FakeWindows())

        result = capability.capture_screen()

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertIn("shot.png", result.message)
        self.assertEqual(tools.calls, [("capture_screen", None, None)])

    def test_capture_screen_unconfirmed_is_flagged(self):
        tools = FakeScreenTools(result={
            "path": "/out/shot.png",
            "bytes": 0,
            "command_executed": True,
            "state_confirmed": False,
        })
        capability = ScreenshotCapability(screen_tools=tools, windows=FakeWindows())

        result = capability.capture_screen()

        self.assertTrue(result.ok)
        self.assertFalse(result.data["state_confirmed"])
        self.assertIn("n'a pas pu confirmer", result.message)

    def test_capture_screen_tool_error(self):
        tools = FakeScreenTools(error=ScreenCaptureError("x", code="capture_failed"))
        capability = ScreenshotCapability(screen_tools=tools, windows=FakeWindows())

        result = capability.capture_screen()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "capture_failed")

    def test_capture_region_invalid_is_tool_failure(self):
        tools = FakeScreenTools(error=ScreenCaptureError("x", code="invalid_region"))
        capability = ScreenshotCapability(screen_tools=tools, windows=FakeWindows())

        result = capability.capture_region(0, 0, 0, 0)

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_region")


class ScreenshotWindowTest(unittest.TestCase):
    def test_capture_active_window_uses_bounds(self):
        tools = FakeScreenTools()
        windows = FakeWindows(active=active_window_result())
        capability = ScreenshotCapability(screen_tools=tools, windows=windows)

        result = capability.capture_window()

        self.assertTrue(result.ok)
        self.assertEqual(result.data["target_app"], "Safari")
        self.assertEqual(
            tools.calls,
            [("capture_region", 5, 10, 800, 600, None)],
        )
        self.assertEqual(windows.calls, [("get_active_window",)])

    def test_capture_named_window_focuses_first(self):
        tools = FakeScreenTools()
        windows = FakeWindows(
            focus=ToolResult.success(action="focus_window", message="ok", state_confirmed=True),
            active=active_window_result(target_app="Notes"),
        )
        capability = ScreenshotCapability(screen_tools=tools, windows=windows)

        result = capability.capture_window(app_name="Notes")

        self.assertTrue(result.ok)
        self.assertEqual(windows.calls[0], ("focus_window", "Notes"))
        self.assertEqual(windows.calls[1], ("get_active_window",))

    def test_capture_window_focus_failure_stops(self):
        tools = FakeScreenTools()
        windows = FakeWindows(
            focus=ToolResult.failure(
                action="focus_window",
                message="introuvable",
                error_code="no_window",
            ),
        )
        capability = ScreenshotCapability(screen_tools=tools, windows=windows)

        result = capability.capture_window(app_name="Ghost")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "no_window")
        self.assertEqual(tools.calls, [])

    def test_capture_window_app_mismatch_stops(self):
        tools = FakeScreenTools()
        windows = FakeWindows(
            focus=ToolResult.success(action="focus_window", message="ok", state_confirmed=True),
            active=active_window_result(target_app="Safari"),
        )
        capability = ScreenshotCapability(screen_tools=tools, windows=windows)

        result = capability.capture_window(app_name="Notes")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "active_window_mismatch")
        self.assertEqual(tools.calls, [])

    def test_capture_window_missing_bounds(self):
        tools = FakeScreenTools()
        active = ToolResult.success(
            action="get_active_window",
            message="x",
            target_app="Safari",
            position={"x": None, "y": 0},
            size={"width": 800, "height": 600},
        )
        windows = FakeWindows(active=active)
        capability = ScreenshotCapability(screen_tools=tools, windows=windows)

        result = capability.capture_window()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "window_bounds_unavailable")
        self.assertEqual(tools.calls, [])


if __name__ == "__main__":
    unittest.main()
