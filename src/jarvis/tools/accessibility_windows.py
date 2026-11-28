"""Focused window lookup and visible window candidates."""
from __future__ import annotations

from typing import Any

from jarvis.tools.accessibility_common import (
    AccessibilityError,
    K_CG_NULL_WINDOW_ID,
    K_CG_WINDOW_LIST_EXCLUDE_DESKTOP_ELEMENTS,
    K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY,
    SYSTEM_WINDOW_OWNERS,
)


class AXWindowsMixin:
    """Focused window lookup and visible window candidates. Mixed into ApplicationServicesAccessibilityBackend."""

    def focused_window(self):
        self.ensure_trusted()
        system_error = None

        try:
            return self._focused_window_from_system_wide()
        except AccessibilityError as error:
            if error.code != "cannot_complete":
                raise

            system_error = error

        try:
            return self._focused_window_from_visible_windows()
        except AccessibilityError as fallback_error:
            raise AccessibilityError(
                (
                    "Impossible de recuperer la fenetre Accessibility active "
                    "depuis l'application frontmost."
                ),
                "focused_window_unavailable",
                {
                    "system_error": system_error.code if system_error else None,
                    "fallback_error": fallback_error.code,
                },
            ) from fallback_error

    def _focused_window_from_system_wide(self):
        system = self.app_services.AXUIElementCreateSystemWide()

        if not system:
            raise AccessibilityError(
                "Impossible de creer l'element Accessibility system-wide.",
                "accessibility_unavailable",
            )

        try:
            app = self.copy_attribute(system, "AXFocusedApplication")
            try:
                return self.copy_attribute(app, "AXFocusedWindow")
            finally:
                self.release(app)
        finally:
            self.release(system)

    def _focused_window_from_visible_windows(self):
        fallback_errors = []

        for candidate in self.visible_window_candidates():
            pid = candidate.get("pid")

            if not pid:
                continue

            app = self.create_application(pid)

            if not app:
                continue

            try:
                return self.copy_attribute(app, "AXFocusedWindow")
            except AccessibilityError as error:
                fallback_errors.append({
                    "pid": pid,
                    "owner": candidate.get("owner"),
                    "error_code": error.code,
                })
            finally:
                self.release(app)

        raise AccessibilityError(
            "Aucune fenetre Accessibility frontmost exploitable n'a ete trouvee.",
            "no_accessibility_window",
            {"candidates": fallback_errors},
        )

    def visible_window_candidates(self) -> list[dict[str, Any]]:
        options = (
            K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY
            | K_CG_WINDOW_LIST_EXCLUDE_DESKTOP_ELEMENTS
        )
        window_info = self.core_graphics.CGWindowListCopyWindowInfo(
            options,
            K_CG_NULL_WINDOW_ID,
        )

        if not window_info:
            return []

        candidates = []

        try:
            count = self.core_foundation.CFArrayGetCount(window_info)

            for index in range(count):
                item = self.core_foundation.CFArrayGetValueAtIndex(
                    window_info,
                    index,
                )

                if not item:
                    continue

                if self.core_foundation.CFGetTypeID(item) != (
                    self.core_foundation.CFDictionaryGetTypeID()
                ):
                    continue

                candidate = {
                    "index": index,
                    "pid": self.cf_dictionary_get_int(item, "kCGWindowOwnerPID"),
                    "owner": self.cf_dictionary_get_text(item, "kCGWindowOwnerName"),
                    "name": self.cf_dictionary_get_text(item, "kCGWindowName"),
                    "layer": self.cf_dictionary_get_int(item, "kCGWindowLayer"),
                    "window_number": self.cf_dictionary_get_int(
                        item,
                        "kCGWindowNumber",
                    ),
                }

                if self.is_plausible_window_candidate(candidate):
                    candidates.append(candidate)
        finally:
            self.release(window_info)

        return candidates

    @staticmethod
    def is_plausible_window_candidate(candidate: dict[str, Any]) -> bool:
        pid = candidate.get("pid")

        if not isinstance(pid, int) or pid <= 0:
            return False

        if candidate.get("layer") != 0:
            return False

        if candidate.get("owner") in SYSTEM_WINDOW_OWNERS:
            return False

        return True
