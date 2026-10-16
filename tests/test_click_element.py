import asyncio
import unittest

from jarvis.capabilities.results import ToolResult
from jarvis.live.registry import create_live_registry


class FakeUIAcc:
    def __init__(self, candidate=None, locate_ok=True):
        self.candidate = candidate or {}
        self.locate_ok = locate_ok
        self.activated = []

    def locate(self, query, role=None):
        if not self.locate_ok:
            return ToolResult.failure(
                action="locate", message="introuvable", error_code="ui_element_not_found",
            )
        return ToolResult.success(action="locate", message="ok", candidate=self.candidate)

    def activate_ui_element(self, query, role=None):
        self.activated.append(query)
        return ToolResult.success(
            action="activate_ui_element", message="ok",
            command_executed=True, state_confirmed=False,
        )


class FakeMouse:
    def __init__(self, move_confirmed=True):
        self.moves = []
        self.clicks = 0
        self.move_confirmed = move_confirmed

    def move_mouse(self, x, y):
        self.moves.append((x, y))
        return ToolResult.success(
            action="move_mouse", message="ok", state_confirmed=self.move_confirmed, x=x, y=y,
        )

    def click(self):
        self.clicks += 1
        return ToolResult.success(
            action="click", message="ok", command_executed=True, state_confirmed=False,
        )


class FakeMemory:
    def log_action(self, *a, **k):
        return None


def tools_with(ui, mouse):
    registry = create_live_registry(
        ui_accessibility_capability=ui,
        mouse_capability=mouse,
        memory_capability=FakeMemory(),
    )
    return {t.info.name: t for t in registry.livekit_tools()}


class ClickElementTests(unittest.TestCase):
    def test_axpress_when_supported(self):
        ui = FakeUIAcc(candidate={"actions": ["AXPress"], "role": "AXButton"})
        mouse = FakeMouse()
        tools = tools_with(ui, mouse)

        result = asyncio.run(tools["click_element"]("Valider"))

        self.assertTrue(result["ok"])
        self.assertEqual(ui.activated, ["Valider"])  # pressed via AX
        self.assertEqual(mouse.clicks, 0)            # no mouse used

    def test_grounded_mouse_click_when_no_axpress(self):
        ui = FakeUIAcc(candidate={
            "actions": [], "role": "AXImage",
            "position": {"x": 100, "y": 200}, "size": {"width": 40, "height": 20},
        })
        mouse = FakeMouse()
        tools = tools_with(ui, mouse)

        result = asyncio.run(tools["click_element"]("logo bleu"))

        self.assertTrue(result["ok"])
        self.assertEqual(mouse.moves, [(120, 210)])  # AX-grounded center
        self.assertEqual(mouse.clicks, 1)
        self.assertEqual(result["grounded"], "accessibility")

    def test_refuses_when_no_action_and_no_position(self):
        ui = FakeUIAcc(candidate={"actions": [], "role": "AXGroup"})
        mouse = FakeMouse()
        tools = tools_with(ui, mouse)

        result = asyncio.run(tools["click_element"]("truc"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "no_grounded_target")
        self.assertEqual(mouse.clicks, 0)  # never blind-clicked

    def test_not_found_returns_failure(self):
        ui = FakeUIAcc(locate_ok=False)
        mouse = FakeMouse()
        tools = tools_with(ui, mouse)

        result = asyncio.run(tools["click_element"]("absent"))
        self.assertFalse(result["ok"])
        self.assertEqual(mouse.clicks, 0)

    def test_move_not_confirmed_aborts_click(self):
        ui = FakeUIAcc(candidate={
            "actions": [], "position": {"x": 0, "y": 0}, "size": {"width": 10, "height": 10},
        })
        mouse = FakeMouse(move_confirmed=False)
        tools = tools_with(ui, mouse)

        result = asyncio.run(tools["click_element"]("x"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "move_failed")
        self.assertEqual(mouse.clicks, 0)  # did not click when move unconfirmed


if __name__ == "__main__":
    unittest.main()
