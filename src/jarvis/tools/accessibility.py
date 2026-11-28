"""Accessibility tools: inspect, find, focus, fill and activate UI elements of the frontmost window.

The AX backend lives in accessibility_backend and the shared constants and
pure helpers in accessibility_common; both are re-exported here.
"""
from __future__ import annotations

import ctypes
import unicodedata
from ctypes import util
from dataclasses import dataclass
from typing import Any

from jarvis.tools.lazy import LazyBackend
from jarvis.tools.accessibility_common import (  # noqa: F401 -- re-exported
    AccessibilityError,
    CGPoint,
    CGSize,
    CFRange,
    strict_int,
    validate_query,
    normalize_text,
    searchable_fields,
    match_elements,
    is_short_exact_query,
    should_include_element,
    compact_element,
    strip_handle,
    strip_handles,
    DEFAULT_UI_MAX_DEPTH,
    DEFAULT_UI_MAX_ELEMENTS,
    MAX_UI_DEPTH,
    MAX_UI_ELEMENTS,
    VALUE_SUMMARY_MAX_CHARS,
    K_CFSTRING_UTF8,
    K_CFNUMBER_SINT32,
    K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY,
    K_CG_WINDOW_LIST_EXCLUDE_DESKTOP_ELEMENTS,
    K_CG_NULL_WINDOW_ID,
    SYSTEM_WINDOW_OWNERS,
    INTERESTING_ROLES,
    TEXT_ROLES,
    SECURE_ROLES,
    SOFT_ATTRIBUTE_ERROR_CODES,
    AX_ERROR_CODES,
)
from jarvis.tools.accessibility_backend import (  # noqa: F401 -- re-exported
    ApplicationServicesAccessibilityBackend,
)


@dataclass
class AccessibilityTools:
    backend: Any | None = None

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = LazyBackend(ApplicationServicesAccessibilityBackend)

    def inspect_ui(
        self,
        max_depth: int = DEFAULT_UI_MAX_DEPTH,
        max_elements: int = DEFAULT_UI_MAX_ELEMENTS,
    ) -> dict[str, Any]:
        max_depth, max_elements = self.validate_limits(max_depth, max_elements)
        root = self.backend.focused_window()

        try:
            result = self._snapshot_tree(root, max_depth, max_elements)
        finally:
            self.backend.release(root)

        result["max_depth"] = max_depth
        result["max_elements"] = max_elements
        return result

    def find_ui_elements(
        self,
        query: str,
        role: str | None = None,
        max_depth: int = DEFAULT_UI_MAX_DEPTH,
        max_elements: int = DEFAULT_UI_MAX_ELEMENTS,
    ) -> dict[str, Any]:
        normalized_query = validate_query(query)
        normalized_role = normalize_text(role) if role else None
        snapshot = self.inspect_ui(max_depth=max_depth, max_elements=max_elements)
        candidates = match_elements(
            snapshot["elements"],
            normalized_query,
            normalized_role,
        )

        if not candidates:
            raise AccessibilityError(
                "Aucun element Accessibility ne correspond a cette recherche.",
                "ui_element_not_found",
                {"query_length": len(query), "role": role},
            )

        return {
            "query_length": len(query),
            "role": role,
            "candidates": candidates,
            "candidate_count": len(candidates),
            "truncated": snapshot["truncated"],
        }

    def focus_ui_element(self, query: str, role: str | None = None) -> dict[str, Any]:
        element, candidate = self._resolve_one(
            query, role, max_depth=MAX_UI_DEPTH, max_elements=MAX_UI_ELEMENTS,
        )

        try:
            if candidate.get("enabled") is False:
                raise AccessibilityError(
                    "L'element Accessibility est desactive.",
                    "ui_element_disabled",
                    {"candidate": candidate},
                )

            self.backend.set_focused(element)
            refreshed = self._snapshot_element(element, candidate["path"])
            confirmed = refreshed.get("focused") is True

            return {
                "command_executed": True,
                "state_confirmed": confirmed,
                "candidate": candidate,
                "element": refreshed,
            }
        finally:
            self.backend.release(element)

    def set_value(self, query: str, value: str, role: str | None = None) -> dict[str, Any]:
        """Write a value into an editable element and confirm it by read-back.

        For apps whose composer does not accept programmatic focus (AXFocused
        never confirms), this sets AXValue directly and verifies the text
        landed, rather than relying on focus + keystrokes.
        """
        element, candidate = self._resolve_one(
            query, role, max_depth=MAX_UI_DEPTH, max_elements=MAX_UI_ELEMENTS,
        )

        try:
            if candidate.get("enabled") is False:
                raise AccessibilityError(
                    "L'element Accessibility est desactive.",
                    "ui_element_disabled",
                    {"candidate": candidate},
                )
            if candidate.get("editable") is False:
                raise AccessibilityError(
                    "Cet element Accessibility n'est pas editable.",
                    "ui_element_not_editable",
                    {"candidate": candidate},
                )

            self.backend.set_value_text(element, value)
            readback = self.backend.copy_attribute_text(element, "AXValue")
            refreshed = self._snapshot_element(element, candidate["path"])

            return {
                "command_executed": True,
                "state_confirmed": readback == value,
                "candidate": candidate,
                "element": refreshed,
            }
        finally:
            self.backend.release(element)

    def locate(self, query: str, role: str | None = None) -> dict[str, Any]:
        """Resolve one element and return its snapshot (role, actions, position,
        size) WITHOUT acting on it. For deciding AXPress vs an AX-grounded click."""
        element, candidate = self._resolve_one(
            query, role, max_depth=MAX_UI_DEPTH, max_elements=MAX_UI_ELEMENTS,
        )
        try:
            return {"candidate": candidate}
        finally:
            self.backend.release(element)

    def read_value(self, query: str, role: str | None = None) -> dict[str, Any]:
        """Read an element's own AXValue (e.g. the composer draft)."""
        element, candidate = self._resolve_one(
            query, role, max_depth=MAX_UI_DEPTH, max_elements=MAX_UI_ELEMENTS,
        )

        try:
            value = self.backend.copy_attribute_text(element, "AXValue")
            return {"command_executed": True, "value": value, "candidate": candidate}
        finally:
            self.backend.release(element)

    def activate_ui_element(self, query: str, role: str | None = None) -> dict[str, Any]:
        # Reach as deep as focus_ui_element: some controls (e.g. a messaging
        # app's send button) sit below the shallow default depth.
        element, candidate = self._resolve_one(
            query, role, max_depth=MAX_UI_DEPTH, max_elements=MAX_UI_ELEMENTS,
        )

        try:
            if candidate.get("enabled") is False:
                raise AccessibilityError(
                    "L'element Accessibility est desactive.",
                    "ui_element_disabled",
                    {"candidate": candidate},
                )

            if "AXPress" not in (candidate.get("actions") or []):
                raise AccessibilityError(
                    "Cet element ne prend pas en charge AXPress.",
                    "ui_action_unsupported",
                    {"candidate": candidate},
                )

            before_selected = candidate.get("selected")
            self.backend.perform_press(element)
            refreshed = self._snapshot_element(element, candidate["path"])
            state_confirmed = False

            if candidate.get("role") in {"AXCheckBox", "AXRadioButton"}:
                after_selected = refreshed.get("selected")
                state_confirmed = (
                    before_selected is not None
                    and after_selected is not None
                    and after_selected != before_selected
                )

            return {
                "command_executed": True,
                "state_confirmed": state_confirmed,
                "candidate": candidate,
                "element": refreshed,
            }
        finally:
            self.backend.release(element)

    def _resolve_one(
        self,
        query: str,
        role: str | None,
        max_depth: int = DEFAULT_UI_MAX_DEPTH,
        max_elements: int = DEFAULT_UI_MAX_ELEMENTS,
    ) -> tuple[Any, dict[str, Any]]:
        normalized_query = validate_query(query)
        normalized_role = normalize_text(role) if role else None
        root = self.backend.focused_window()

        try:
            snapshot = self._snapshot_tree(
                root,
                max_depth,
                max_elements,
                retain_matches=True,
            )
            candidates = match_elements(
                snapshot["elements"],
                normalized_query,
                normalized_role,
            )

            if not candidates:
                raise AccessibilityError(
                    "Aucun element Accessibility ne correspond a cette recherche.",
                    "ui_element_not_found",
                    {"query_length": len(query), "role": role},
                )

            if len(candidates) > 1:
                raise AccessibilityError(
                    "Plusieurs elements Accessibility correspondent a cette recherche.",
                    "ambiguous_ui_element",
                    {"candidates": strip_handles(candidates)},
                )

            candidate = candidates[0]
            handle = candidate.get("_handle")

            if handle is None:
                raise AccessibilityError(
                    "L'element Accessibility n'est plus disponible.",
                    "stale_ui_element",
                )

            retained = self.backend.retain(handle)
            return retained, strip_handle(candidate)
        finally:
            self._release_snapshot_handles(snapshot if "snapshot" in locals() else None)
            self.backend.release(root)

    def _snapshot_tree(
        self,
        root,
        max_depth: int,
        max_elements: int,
        retain_matches: bool = False,
    ) -> dict[str, Any]:
        elements = []
        diagnostics = []
        truncated = False
        focused_element = None

        def visit(element, path: list[int], depth: int) -> None:
            nonlocal truncated, focused_element

            if len(elements) >= max_elements:
                truncated = True
                return

            try:
                snapshot = self._snapshot_element(element, path)
            except AccessibilityError as error:
                diagnostics.append({
                    "path": path,
                    "error_code": error.code,
                })
                return

            if should_include_element(snapshot):
                snapshot["element_id"] = f"ephemeral-{len(elements) + 1}"

                if retain_matches:
                    snapshot["_handle"] = self.backend.retain(element)

                elements.append(snapshot)

                if snapshot.get("focused"):
                    focused_element = strip_handle(snapshot)

            if depth >= max_depth:
                return

            try:
                children = self.backend.children(element)
            except AccessibilityError as error:
                diagnostics.append({
                    "path": path,
                    "error_code": error.code,
                })
                return

            for index, child in enumerate(children):
                try:
                    visit(child, [*path, index], depth + 1)
                finally:
                    self.backend.release(child)

        visit(root, [], 0)

        return {
            "elements": elements if retain_matches else [strip_handle(item) for item in elements],
            "count": len(elements),
            "truncated": truncated,
            "focused_element": focused_element,
            "diagnostics": diagnostics,
        }

    def _snapshot_element(self, element, path: list[int]) -> dict[str, Any]:
        return compact_element(dict(self.backend.element_snapshot(element, path)))

    def _release_snapshot_handles(self, snapshot: dict[str, Any] | None) -> None:
        if snapshot is None:
            return

        for element in snapshot.get("elements", []):
            handle = element.get("_handle")

            if handle is not None:
                self.backend.release(handle)

    @staticmethod
    def validate_limits(max_depth: int, max_elements: int) -> tuple[int, int]:
        if not strict_int(max_depth) or not 0 <= max_depth <= MAX_UI_DEPTH:
            raise AccessibilityError(
                f"max_depth doit etre un entier entre 0 et {MAX_UI_DEPTH}.",
                "invalid_ui_max_depth",
            )

        if not strict_int(max_elements) or not 1 <= max_elements <= MAX_UI_ELEMENTS:
            raise AccessibilityError(
                f"max_elements doit etre un entier entre 1 et {MAX_UI_ELEMENTS}.",
                "invalid_ui_max_elements",
            )

        return max_depth, max_elements
