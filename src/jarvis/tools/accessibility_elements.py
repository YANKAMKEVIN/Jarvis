"""Element snapshots, children and element actions (press, focus, set value)."""
from __future__ import annotations

import ctypes
from typing import Any

from jarvis.tools.accessibility_common import (
    AccessibilityError,
    SECURE_ROLES,
    TEXT_ROLES,
    compact_element,
)


class AXElementsMixin:
    """Element snapshots, children and element actions (press, focus, set value). Mixed into ApplicationServicesAccessibilityBackend."""

    def element_snapshot(self, element, path: list[int]) -> dict[str, Any]:
        role = self.copy_attribute_text(element, "AXRole")
        subrole = self.copy_attribute_text(element, "AXSubrole")
        title = self.copy_attribute_text(element, "AXTitle")
        description = self.copy_attribute_text(element, "AXDescription")
        identifier = self.copy_attribute_text(element, "AXIdentifier")
        enabled = self.copy_attribute_bool(element, "AXEnabled")
        focused = self.copy_attribute_bool(element, "AXFocused")
        selected = self.copy_attribute_bool(element, "AXSelected")
        position = self.copy_attribute_point(element, "AXPosition")
        size = self.copy_attribute_size(element, "AXSize")
        actions = self.action_names(element)
        secure = role in SECURE_ROLES

        return compact_element({
            "role": role,
            "subrole": subrole,
            "title": title,
            "description": description,
            "identifier": identifier,
            "enabled": enabled,
            "focused": focused,
            "selected": selected,
            "position": position,
            "size": size,
            "actions": actions,
            "path": list(path),
            "secure": secure,
            "editable": self.value_is_settable(element) if role in TEXT_ROLES else None,
            "value_summary": None,
        })

    def value_is_settable(self, element) -> bool:
        attribute = self.cf_string("AXValue")
        settable = ctypes.c_bool(False)
        try:
            status = self.app_services.AXUIElementIsAttributeSettable(
                element, attribute, ctypes.byref(settable),
            )
            return status == 0 and settable.value
        finally:
            self.release(attribute)

    def children(self, element) -> list[Any]:
        try:
            array = self.copy_attribute(element, "AXChildren")
        except AccessibilityError as error:
            if error.code in {"attribute_unsupported", "no_value"}:
                return []
            raise

        children = []

        try:
            count = self.core_foundation.CFArrayGetCount(array)

            for index in range(count):
                child = self.core_foundation.CFArrayGetValueAtIndex(array, index)

                if child:
                    children.append(self.core_foundation.CFRetain(child))
        finally:
            self.release(array)

        return children

    def perform_press(self, element) -> None:
        action = self.cf_string("AXPress")

        try:
            status = self.app_services.AXUIElementPerformAction(element, action)
        finally:
            self.release(action)

        self.raise_for_status(status, "AXPress")

    def set_focused(self, element) -> None:
        attribute = self.cf_string("AXFocused")

        try:
            status = self.app_services.AXUIElementSetAttributeValue(
                element,
                attribute,
                self._cf_true,
            )
        finally:
            self.release(attribute)

        self.raise_for_status(status, "AXFocused")

    def set_value_text(self, element, value: str) -> None:
        attribute = self.cf_string("AXValue")
        cf_value = self.cf_string(value)

        try:
            status = self.app_services.AXUIElementSetAttributeValue(
                element,
                attribute,
                cf_value,
            )
        finally:
            self.release(attribute)
            self.release(cf_value)

        self.raise_for_status(status, "AXValue")

    def action_names(self, element) -> list[str]:
        actions = ctypes.c_void_p()
        status = self.app_services.AXUIElementCopyActionNames(
            element,
            ctypes.byref(actions),
        )

        if status != 0:
            code = self.status_code(status)

            if code in {"action_unsupported", "no_value"}:
                return []

            raise AccessibilityError(
                "Impossible de lire les actions Accessibility.",
                code,
            )

        try:
            converted = self.cf_to_python(actions.value)

            if isinstance(converted, list):
                return [item for item in converted if isinstance(item, str)]

            return []
        finally:
            if actions.value:
                self.release(actions.value)
