import unittest
from unittest import mock

from jarvis.tools.accessibility import AccessibilityError, AccessibilityTools
from jarvis.tools.lazy import LazyBackend
from jarvis.tools.mouse import MouseError, MouseTools


class LazyBackendTest(unittest.TestCase):
    def test_factory_runs_once_on_first_use(self):
        calls = []

        class Backend:
            value = 42

        def factory():
            calls.append(1)
            return Backend()

        backend = LazyBackend(factory)
        self.assertEqual(calls, [])
        self.assertEqual(backend.value, 42)
        self.assertEqual(backend.value, 42)
        self.assertEqual(calls, [1])

    def test_mouse_tools_build_without_core_graphics(self):
        with mock.patch("jarvis.tools.mouse.util.find_library", return_value=None):
            tools = MouseTools()

            with self.assertRaises(MouseError):
                tools.get_position()

    def test_accessibility_tools_build_without_application_services(self):
        with mock.patch(
            "jarvis.tools.accessibility.util.find_library", return_value=None
        ):
            tools = AccessibilityTools()

            with self.assertRaises(AccessibilityError):
                tools.inspect_ui()


if __name__ == "__main__":
    unittest.main()
