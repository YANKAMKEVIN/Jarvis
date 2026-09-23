from __future__ import annotations

import ctypes
from ctypes import util
from dataclasses import dataclass
from typing import Any


MAX_SCROLL_AMOUNT = 10
MOUSE_POSITION_TOLERANCE_POINTS = 2

SCROLL_DIRECTIONS = {"up", "down", "left", "right"}


class MouseError(Exception):
    def __init__(
        self,
        message: str,
        code: str,
        data: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}


class CGPoint(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
    ]


class CGSize(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
    ]


class CGRect(ctypes.Structure):
    _fields_ = [
        ("origin", CGPoint),
        ("size", CGSize),
    ]


class CoreGraphicsMouseBackend:
    kCGHIDEventTap = 0
    kCGEventLeftMouseDown = 1
    kCGEventLeftMouseUp = 2
    kCGEventRightMouseDown = 3
    kCGEventRightMouseUp = 4
    kCGEventMouseMoved = 5
    kCGMouseButtonLeft = 0
    kCGMouseButtonRight = 1
    kCGMouseEventClickState = 1
    kCGScrollEventUnitLine = 1
    kCGNullDirectDisplay = 0

    def __init__(self, core_graphics=None, core_foundation=None):
        self.core_graphics = (
            core_graphics
            if core_graphics is not None
            else self._load_framework("CoreGraphics")
        )
        self.core_foundation = (
            core_foundation
            if core_foundation is not None
            else self._load_framework("CoreFoundation")
        )
        self._configure_signatures()

    @staticmethod
    def _load_framework(name: str):
        path = util.find_library(name)

        if path is None:
            raise MouseError(
                f"Le framework macOS {name} est indisponible.",
                "framework_missing",
            )

        return ctypes.CDLL(path)

    def _configure_signatures(self) -> None:
        cg = self.core_graphics

        cg.CGEventCreate.argtypes = [ctypes.c_void_p]
        cg.CGEventCreate.restype = ctypes.c_void_p
        cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
        cg.CGEventGetLocation.restype = CGPoint
        cg.CGEventCreateMouseEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            CGPoint,
            ctypes.c_uint32,
        ]
        cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        cg.CGEventCreateScrollWheelEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_int32,
            ctypes.c_int32,
        ]
        cg.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
        cg.CGEventSetIntegerValueField.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_int64,
        ]
        cg.CGEventSetIntegerValueField.restype = None
        cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        cg.CGEventPost.restype = None
        cg.CGGetActiveDisplayList.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        cg.CGGetActiveDisplayList.restype = ctypes.c_int32
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGDisplayBounds.restype = CGRect

        self.core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        self.core_foundation.CFRelease.restype = None

    def get_position(self) -> tuple[int, int]:
        event = self.core_graphics.CGEventCreate(None)

        if not event:
            raise MouseError(
                "Impossible de lire la position de la souris.",
                "core_graphics_error",
            )

        try:
            point = self.core_graphics.CGEventGetLocation(event)
            return round(point.x), round(point.y)
        finally:
            self.core_foundation.CFRelease(event)

    def screens(self) -> list[dict[str, int]]:
        max_displays = 32
        display_ids = (ctypes.c_uint32 * max_displays)()
        display_count = ctypes.c_uint32(0)
        status = self.core_graphics.CGGetActiveDisplayList(
            max_displays,
            display_ids,
            ctypes.byref(display_count),
        )

        if status != 0:
            raise MouseError(
                "Impossible de lire la liste des ecrans.",
                "core_graphics_error",
            )

        screens = []

        for index in range(display_count.value):
            bounds = self.core_graphics.CGDisplayBounds(display_ids[index])
            screens.append({
                "screen_index": index,
                "display_id": int(display_ids[index]),
                "x": round(bounds.origin.x),
                "y": round(bounds.origin.y),
                "width": round(bounds.size.width),
                "height": round(bounds.size.height),
            })

        if not screens:
            raise MouseError("Aucun ecran disponible.", "no_screen")

        return screens

    def move(self, x: int, y: int) -> None:
        event = self._create_mouse_event(
            self.kCGEventMouseMoved,
            x,
            y,
            self.kCGMouseButtonLeft,
        )
        self._post_and_release(event)

    def click(self, button: str = "left", click_count: int = 1) -> None:
        x, y = self.get_position()
        event_types, cg_button = self._button_event_types(button)

        for state in range(1, click_count + 1):
            down = self._create_mouse_event(event_types[0], x, y, cg_button)
            up = self._create_mouse_event(event_types[1], x, y, cg_button)
            self.core_graphics.CGEventSetIntegerValueField(
                down,
                self.kCGMouseEventClickState,
                state,
            )
            self.core_graphics.CGEventSetIntegerValueField(
                up,
                self.kCGMouseEventClickState,
                state,
            )
            self._post_and_release(down)
            self._post_and_release(up)

    def scroll(self, direction: str, amount: int) -> None:
        vertical = 0
        horizontal = 0

        if direction == "up":
            vertical = amount
        elif direction == "down":
            vertical = -amount
        elif direction == "left":
            horizontal = -amount
        elif direction == "right":
            horizontal = amount
        else:
            raise MouseError("Direction de scroll invalide.", "invalid_scroll_direction")

        event = self.core_graphics.CGEventCreateScrollWheelEvent(
            None,
            self.kCGScrollEventUnitLine,
            2,
            vertical,
            horizontal,
        )

        if not event:
            raise MouseError(
                "Impossible de creer l'evenement de scroll.",
                "core_graphics_error",
            )

        self._post_and_release(event)

    def _create_mouse_event(
        self,
        event_type: int,
        x: int,
        y: int,
        button: int,
    ):
        event = self.core_graphics.CGEventCreateMouseEvent(
            None,
            event_type,
            CGPoint(float(x), float(y)),
            button,
        )

        if not event:
            raise MouseError(
                "Impossible de creer l'evenement souris.",
                "core_graphics_error",
            )

        return event

    def _post_and_release(self, event) -> None:
        try:
            self.core_graphics.CGEventPost(self.kCGHIDEventTap, event)
        except PermissionError as error:
            raise MouseError(
                "Permission Accessibility refusee pour la souris.",
                "accessibility_permission_error",
            ) from error
        finally:
            self.core_foundation.CFRelease(event)

    def _button_event_types(self, button: str) -> tuple[tuple[int, int], int]:
        if button == "left":
            return (
                (self.kCGEventLeftMouseDown, self.kCGEventLeftMouseUp),
                self.kCGMouseButtonLeft,
            )

        if button == "right":
            return (
                (self.kCGEventRightMouseDown, self.kCGEventRightMouseUp),
                self.kCGMouseButtonRight,
            )

        raise MouseError("Bouton souris invalide.", "invalid_mouse_button")


@dataclass
class MouseTools:
    backend: Any | None = None
    max_scroll_amount: int = MAX_SCROLL_AMOUNT
    tolerance_points: int = MOUSE_POSITION_TOLERANCE_POINTS

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = CoreGraphicsMouseBackend()

    def get_position(self) -> dict[str, Any]:
        x, y = self.backend.get_position()
        screen = self._screen_for_point(x, y)

        return {
            "x": x,
            "y": y,
            "screen_index": screen.get("screen_index") if screen else None,
        }

    def move(self, x: int, y: int) -> dict[str, Any]:
        target_x, target_y = self.validate_coordinates(x, y)
        before = self.get_position()

        self.backend.move(target_x, target_y)
        after = self.get_position()
        confirmed = self._point_matches(after["x"], after["y"], target_x, target_y)

        return {
            "command_executed": True,
            "state_confirmed": confirmed,
            "previous_x": before["x"],
            "previous_y": before["y"],
            "target_x": target_x,
            "target_y": target_y,
            "x": after["x"],
            "y": after["y"],
            "screen_index": after.get("screen_index"),
        }

    def click(self) -> dict[str, Any]:
        position = self.get_position()
        self.backend.click(button="left", click_count=1)

        return {
            "command_executed": True,
            "state_confirmed": False,
            "button": "left",
            "click_count": 1,
            **position,
        }

    def double_click(self) -> dict[str, Any]:
        position = self.get_position()
        self.backend.click(button="left", click_count=2)

        return {
            "command_executed": True,
            "state_confirmed": False,
            "button": "left",
            "click_count": 2,
            **position,
        }

    def right_click(self) -> dict[str, Any]:
        position = self.get_position()
        self.backend.click(button="right", click_count=1)

        return {
            "command_executed": True,
            "state_confirmed": False,
            "button": "right",
            "click_count": 1,
            **position,
        }

    def scroll(self, direction: str, amount: int = 3) -> dict[str, Any]:
        normalized_direction = self.validate_scroll_direction(direction)
        normalized_amount = self.validate_scroll_amount(amount)
        position = self.get_position()

        self.backend.scroll(normalized_direction, normalized_amount)

        return {
            "command_executed": True,
            "state_confirmed": False,
            "direction": normalized_direction,
            "amount": normalized_amount,
            **position,
        }

    def validate_coordinates(self, x: int, y: int) -> tuple[int, int]:
        if not self._is_strict_int(x) or not self._is_strict_int(y):
            raise MouseError(
                "Les coordonnees souris doivent etre des entiers.",
                "invalid_coordinates",
            )

        if self._screen_for_point(x, y) is None:
            raise MouseError(
                "Les coordonnees souris sont hors de tous les ecrans disponibles.",
                "coordinates_out_of_bounds",
                {"x": x, "y": y},
            )

        return x, y

    @staticmethod
    def validate_scroll_direction(direction: str) -> str:
        if not isinstance(direction, str):
            raise MouseError("Direction de scroll invalide.", "invalid_scroll_direction")

        normalized = direction.strip().lower()

        if normalized not in SCROLL_DIRECTIONS:
            raise MouseError("Direction de scroll invalide.", "invalid_scroll_direction")

        return normalized

    def validate_scroll_amount(self, amount: int) -> int:
        if not self._is_strict_int(amount):
            raise MouseError("Quantite de scroll invalide.", "invalid_scroll_amount")

        if not 1 <= amount <= self.max_scroll_amount:
            raise MouseError(
                f"La quantite de scroll doit etre comprise entre 1 et {self.max_scroll_amount}.",
                "scroll_amount_out_of_bounds",
                {"amount": amount, "max_amount": self.max_scroll_amount},
            )

        return amount

    def _screen_for_point(self, x: int, y: int) -> dict[str, int] | None:
        for screen in self.backend.screens():
            if (
                screen["x"] <= x < screen["x"] + screen["width"]
                and screen["y"] <= y < screen["y"] + screen["height"]
            ):
                return screen

        return None

    def _point_matches(
        self,
        observed_x: int,
        observed_y: int,
        target_x: int,
        target_y: int,
    ) -> bool:
        return (
            abs(observed_x - target_x) <= self.tolerance_points
            and abs(observed_y - target_y) <= self.tolerance_points
        )

    @staticmethod
    def _is_strict_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)
