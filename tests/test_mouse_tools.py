import unittest

from jarvis.tools.mouse import (
    CoreGraphicsMouseBackend,
    MouseError,
    MouseTools,
)


class FakeMouseBackend:
    def __init__(self):
        self.positions = [(100, 100)]
        self.screen_state = [
            {"screen_index": 0, "x": 0, "y": 0, "width": 1512, "height": 982},
            {"screen_index": 1, "x": -1200, "y": 0, "width": 1200, "height": 900},
        ]
        self.moves = []
        self.clicks = []
        self.scrolls = []

    def get_position(self):
        return self.positions.pop(0) if self.positions else (100, 100)

    def screens(self):
        return list(self.screen_state)

    def move(self, x, y):
        self.moves.append((x, y))

    def click(self, button="left", click_count=1):
        self.clicks.append((button, click_count))

    def scroll(self, direction, amount):
        self.scrolls.append((direction, amount))


class FakeCoreGraphics:
    def __init__(self):
        self.created = []
        self.set_fields = []
        self.posted = []

    def CGEventCreateMouseEvent(self, _source, event_type, point, button):
        event = {
            "type": event_type,
            "x": point.x,
            "y": point.y,
            "button": button,
        }
        self.created.append(event)
        return event

    def CGEventSetIntegerValueField(self, event, field, value):
        self.set_fields.append((event["type"], field, value))

    def CGEventPost(self, tap, event):
        self.posted.append((tap, event["type"]))


class FakeCoreFoundation:
    def __init__(self):
        self.released = []

    def CFRelease(self, event):
        self.released.append(event)


class MouseToolsTest(unittest.TestCase):
    def test_get_position_returns_screen_index_for_primary_screen(self):
        backend = FakeMouseBackend()
        backend.positions = [(742, 431)]
        tools = MouseTools(backend=backend)

        result = tools.get_position()

        self.assertEqual(result["x"], 742)
        self.assertEqual(result["y"], 431)
        self.assertEqual(result["screen_index"], 0)

    def test_get_position_supports_secondary_screen_and_negative_coordinates(self):
        backend = FakeMouseBackend()
        backend.positions = [(-800, 200)]
        tools = MouseTools(backend=backend)

        result = tools.get_position()

        self.assertEqual(result["screen_index"], 1)

    def test_move_confirmed(self):
        backend = FakeMouseBackend()
        backend.positions = [(100, 100), (742, 431)]
        tools = MouseTools(backend=backend)

        result = tools.move(742, 431)

        self.assertEqual(backend.moves, [(742, 431)])
        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertEqual(result["previous_x"], 100)
        self.assertEqual(result["previous_y"], 100)
        self.assertEqual(result["target_x"], 742)
        self.assertEqual(result["target_y"], 431)
        self.assertEqual(result["x"], 742)
        self.assertEqual(result["y"], 431)

    def test_move_non_confirmed(self):
        backend = FakeMouseBackend()
        backend.positions = [(100, 100), (200, 200)]
        tools = MouseTools(backend=backend)

        result = tools.move(742, 431)

        self.assertEqual(backend.moves, [(742, 431)])
        self.assertFalse(result["state_confirmed"])

    def test_validate_coordinates_rejects_non_int_and_bool(self):
        tools = MouseTools(backend=FakeMouseBackend())

        for x, y in (("1", 2), (True, 2), (1, False)):
            with self.subTest(x=x, y=y):
                with self.assertRaises(MouseError) as context:
                    tools.validate_coordinates(x, y)

                self.assertEqual(context.exception.code, "invalid_coordinates")

    def test_validate_coordinates_rejects_out_of_bounds(self):
        tools = MouseTools(backend=FakeMouseBackend())

        with self.assertRaises(MouseError) as context:
            tools.validate_coordinates(9999, 9999)

        self.assertEqual(context.exception.code, "coordinates_out_of_bounds")

    def test_click_variants_delegate_to_backend(self):
        backend = FakeMouseBackend()
        tools = MouseTools(backend=backend)

        click = tools.click()
        double_click = tools.double_click()
        right_click = tools.right_click()

        self.assertEqual(
            backend.clicks,
            [("left", 1), ("left", 2), ("right", 1)],
        )
        self.assertEqual(click["button"], "left")
        self.assertEqual(click["click_count"], 1)
        self.assertFalse(click["state_confirmed"])
        self.assertEqual(double_click["click_count"], 2)
        self.assertEqual(right_click["button"], "right")

    def test_scroll_directions(self):
        backend = FakeMouseBackend()
        tools = MouseTools(backend=backend)

        for direction in ("up", "down", "left", "right"):
            with self.subTest(direction=direction):
                result = tools.scroll(direction, 3)
                self.assertEqual(result["direction"], direction)
                self.assertEqual(result["amount"], 3)
                self.assertFalse(result["state_confirmed"])

        self.assertEqual(
            backend.scrolls,
            [("up", 3), ("down", 3), ("left", 3), ("right", 3)],
        )

    def test_scroll_rejects_invalid_direction_amount_and_bool(self):
        tools = MouseTools(backend=FakeMouseBackend())

        with self.assertRaises(MouseError) as context:
            tools.validate_scroll_direction("diagonal")
        self.assertEqual(context.exception.code, "invalid_scroll_direction")

        for amount in (0, 11, True, "3"):
            with self.subTest(amount=amount):
                with self.assertRaises(MouseError) as context:
                    tools.validate_scroll_amount(amount)

                self.assertIn(
                    context.exception.code,
                    {"invalid_scroll_amount", "scroll_amount_out_of_bounds"},
                )

    def test_backend_double_click_sets_click_state(self):
        backend = CoreGraphicsMouseBackend.__new__(CoreGraphicsMouseBackend)
        backend.core_graphics = FakeCoreGraphics()
        backend.core_foundation = FakeCoreFoundation()
        backend.get_position = lambda: (10, 20)

        backend.click(button="left", click_count=2)

        self.assertEqual(
            [value for _event_type, _field, value in backend.core_graphics.set_fields],
            [1, 1, 2, 2],
        )
        self.assertEqual(len(backend.core_graphics.posted), 4)
        self.assertEqual(len(backend.core_foundation.released), 4)

    def test_backend_scroll_maps_vertical_and_horizontal_axes(self):
        class ScrollCoreGraphics(FakeCoreGraphics):
            def __init__(self):
                super().__init__()
                self.scroll_events = []

            def CGEventCreateScrollWheelEvent(
                self,
                _source,
                unit,
                wheel_count,
                vertical,
                horizontal,
            ):
                event = {
                    "type": "scroll",
                    "unit": unit,
                    "wheel_count": wheel_count,
                    "vertical": vertical,
                    "horizontal": horizontal,
                }
                self.scroll_events.append(event)
                return event

        backend = CoreGraphicsMouseBackend.__new__(CoreGraphicsMouseBackend)
        backend.core_graphics = ScrollCoreGraphics()
        backend.core_foundation = FakeCoreFoundation()

        backend.scroll("up", 4)
        backend.scroll("down", 4)
        backend.scroll("left", 4)
        backend.scroll("right", 4)

        self.assertEqual(
            [
                (event["vertical"], event["horizontal"])
                for event in backend.core_graphics.scroll_events
            ],
            [(4, 0), (-4, 0), (0, -4), (0, 4)],
        )


if __name__ == "__main__":
    unittest.main()
