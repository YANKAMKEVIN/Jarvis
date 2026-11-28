"""Pure window geometry checks and argument validation."""

from jarvis.tools.macos_base import (
    WINDOW_GEOMETRY_TOLERANCE_PIXELS,
)


class WindowGeometryMixin:
    """Pure window geometry checks and argument validation. Mixed into MacOSTools."""

    @staticmethod
    def _window_action_state(
        action_state: dict,
        before_state: dict,
        command_executed: bool,
        state_confirmed: bool,
        requested_position: str | None = None,
        target_position: dict | None = None,
        target_size: dict | None = None,
        diagnostics: dict | None = None,
    ) -> dict:
        state = dict(action_state)
        state["command_executed"] = command_executed
        state["state_confirmed"] = state_confirmed
        state["previous_position"] = before_state.get("position")
        state["previous_size"] = before_state.get("size")
        state["previous_fullscreen"] = before_state.get("fullscreen")
        state["previous_minimized"] = before_state.get("minimized")

        if requested_position is not None:
            state["requested_position"] = requested_position

        if target_position is not None:
            state["target_position"] = target_position

        if target_size is not None:
            state["target_size"] = target_size

        if diagnostics is not None:
            state.update(diagnostics)

        return state

    @staticmethod
    def _window_rect_matches(state: dict, rect: dict) -> bool:
        position = state.get("position") or {}
        size = state.get("size") or {}
        target_position = rect["position"]
        target_size = rect["size"]

        pairs = (
            (position.get("x"), target_position["x"]),
            (position.get("y"), target_position["y"]),
            (size.get("width"), target_size["width"]),
            (size.get("height"), target_size["height"]),
        )

        if any(observed is None for observed, _expected in pairs):
            return False

        return all(
            abs(observed - expected) <= WINDOW_GEOMETRY_TOLERANCE_PIXELS
            for observed, expected in pairs
        )

    @staticmethod
    def _window_geometry_complete(state: dict | None) -> bool:
        if state is None:
            return False

        position = state.get("position") or {}
        size = state.get("size") or {}

        x = position.get("x")
        y = position.get("y")
        width = size.get("width")
        height = size.get("height")

        return (
            isinstance(x, int | float)
            and isinstance(y, int | float)
            and isinstance(width, int | float)
            and isinstance(height, int | float)
            and x >= 0
            and y >= 0
            and width > 0
            and height > 0
        )

    @staticmethod
    def _window_geometry_stable(current: dict | None, previous: dict | None) -> bool:
        if current is None or previous is None:
            return False

        if not (
            WindowGeometryMixin._window_geometry_complete(current)
            and WindowGeometryMixin._window_geometry_complete(previous)
        ):
            return False

        current_position = current["position"]
        previous_position = previous["position"]
        current_size = current["size"]
        previous_size = previous["size"]
        pairs = (
            (current_position["x"], previous_position["x"]),
            (current_position["y"], previous_position["y"]),
            (current_size["width"], previous_size["width"]),
            (current_size["height"], previous_size["height"]),
        )

        return all(
            abs(current_value - previous_value) <= WINDOW_GEOMETRY_TOLERANCE_PIXELS
            for current_value, previous_value in pairs
        )

    @staticmethod
    def _window_candidate_consistent(
        current: dict | None,
        previous: dict | None,
    ) -> bool:
        if current is None or previous is None:
            return False

        if current.get("target_app") != previous.get("target_app"):
            return False

        if current.get("window_role") != previous.get("window_role"):
            return False

        if current.get("window_subrole") != previous.get("window_subrole"):
            return False

        current_title = current.get("window_title")
        previous_title = previous.get("window_title")

        if current_title and previous_title and current_title != previous_title:
            return False

        return True

    @staticmethod
    def _validate_window_app_name(app_name: str) -> str:
        if not isinstance(app_name, str) or not app_name.strip():
            raise ValueError("Nom d'application manquant.")

        return app_name.strip()

    @staticmethod
    def _validate_window_position(position: str) -> str:
        if not isinstance(position, str):
            raise ValueError("Position de fenetre non supportee.")

        normalized = position.strip().lower()

        if normalized not in {"left", "right", "center", "fullscreen"}:
            raise ValueError("Position de fenetre non supportee.")

        return normalized
