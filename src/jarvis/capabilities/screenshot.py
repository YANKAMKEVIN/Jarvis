from __future__ import annotations

import os
from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.windows import WindowCapability
from jarvis.tools.screenshot import ScreenCaptureError, ScreenCaptureTools


class ScreenshotCapability:
    """Capture the screen, a region, or a window to a PNG file.

    Every capture reads the written file back (existence and byte size) and
    reports state_confirmed from it, so a sent command is never mistaken for a
    saved screenshot. Window capture resolves the window bounds first and
    verifies the active application before capturing.
    """

    def __init__(
        self,
        screen_tools: ScreenCaptureTools | None = None,
        windows: WindowCapability | None = None,
    ):
        self.screen_tools = (
            screen_tools if screen_tools is not None else ScreenCaptureTools()
        )
        self.windows = windows if windows is not None else WindowCapability()

    def capture_screen(
        self,
        path: str | None = None,
        display: int | None = None,
    ) -> ToolResult:
        try:
            state = self.screen_tools.capture_screen(path, display)
        except ScreenCaptureError as error:
            return self._tool_failure("capture_screen", error)
        except Exception as error:
            return self._system_error("capture_screen", error)

        return self._capture_result("capture_screen", state)

    def capture_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        path: str | None = None,
    ) -> ToolResult:
        try:
            state = self.screen_tools.capture_region(x, y, width, height, path)
        except ScreenCaptureError as error:
            return self._tool_failure("capture_region", error)
        except Exception as error:
            return self._system_error("capture_region", error)

        return self._capture_result("capture_region", state)

    def capture_window(
        self,
        app_name: str | None = None,
        path: str | None = None,
    ) -> ToolResult:
        if app_name is not None:
            focused = self.windows.focus_window(app_name)

            if not focused.ok:
                return self._dependency_failure("capture_window", "focus_window", focused)

        active = self.windows.get_active_window()

        if not active.ok:
            return self._dependency_failure(
                "capture_window",
                "get_active_window",
                active,
            )

        observed_app = active.data.get("target_app")

        if app_name is not None and not self._same_app(app_name, observed_app):
            return ToolResult.failure(
                action="capture_window",
                message=(
                    "La fenetre active ne correspond pas a l'application demandee. "
                    "La capture a ete arretee."
                ),
                error_code="active_window_mismatch",
            )

        bounds = self._window_bounds(active.data)

        if bounds is None:
            return ToolResult.failure(
                action="capture_window",
                message="Les dimensions de la fenetre active n'ont pas pu etre lues.",
                error_code="window_bounds_unavailable",
            )

        try:
            state = self.screen_tools.capture_region(
                bounds["x"],
                bounds["y"],
                bounds["width"],
                bounds["height"],
                path,
            )
        except ScreenCaptureError as error:
            return self._tool_failure("capture_window", error)
        except Exception as error:
            return self._system_error("capture_window", error)

        state["target_app"] = observed_app
        state["window_title"] = active.data.get("window_title")

        return self._capture_result("capture_window", state)

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _capture_result(action: str, state: dict[str, Any]) -> ToolResult:
        if state.get("state_confirmed"):
            message = (
                "La capture a ete enregistree dans "
                f"{os.path.basename(state['path'])}."
            )
        else:
            message = (
                "La commande de capture a ete envoyee, mais Jarvis n'a pas pu "
                "confirmer l'enregistrement du fichier."
            )

        return ToolResult.success(action=action, message=message, **state)

    @staticmethod
    def _window_bounds(data: dict[str, Any]) -> dict[str, int] | None:
        position = data.get("position") or {}
        size = data.get("size") or {}
        x = position.get("x")
        y = position.get("y")
        width = size.get("width")
        height = size.get("height")

        if None in (x, y, width, height):
            return None

        if width <= 0 or height <= 0:
            return None

        return {"x": int(x), "y": int(y), "width": int(width), "height": int(height)}

    @staticmethod
    def _same_app(expected: str, observed: Any) -> bool:
        if not isinstance(expected, str) or not isinstance(observed, str):
            return False

        return expected.strip().casefold() == observed.strip().casefold()

    @staticmethod
    def _dependency_failure(action: str, step: str, result: ToolResult) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=(
                f"L'etape {step} a echoue, la capture n'a pas ete lancee : "
                f"{result.message}"
            ),
            error_code=result.error_code or "dependency_failed",
        )

    @staticmethod
    def _tool_failure(action: str, error: ScreenCaptureError) -> ToolResult:
        return ToolResult(
            ok=False,
            action=action,
            message=error.message,
            data=dict(error.data),
            error_code=error.code or "screenshot_error",
        )

    @staticmethod
    def _system_error(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action,
            message=f"Echec de la capture d'ecran : {error}",
            error_code="system_error",
        )
