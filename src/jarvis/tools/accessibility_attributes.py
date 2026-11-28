"""AX attribute reads and CoreFoundation conversions."""
from __future__ import annotations

import ctypes

from jarvis.tools.accessibility_common import (
    AccessibilityError,
    CGPoint,
    CGSize,
    K_CFNUMBER_SINT32,
    K_CFSTRING_UTF8,
    SOFT_ATTRIBUTE_ERROR_CODES,
)


class AXAttributesMixin:
    """AX attribute reads and CoreFoundation conversions. Mixed into ApplicationServicesAccessibilityBackend."""

    def copy_attribute(self, element, attribute: str):
        value = ctypes.c_void_p()
        attribute_name = self.cf_string(attribute)

        try:
            status = self.app_services.AXUIElementCopyAttributeValue(
                element,
                attribute_name,
                ctypes.byref(value),
            )
        finally:
            self.release(attribute_name)

        if status != 0:
            self.raise_for_status(status, attribute)

        return value.value

    def copy_attribute_text(self, element, attribute: str) -> str | None:
        try:
            value = self.copy_attribute(element, attribute)
        except AccessibilityError as error:
            if error.code in SOFT_ATTRIBUTE_ERROR_CODES:
                return None
            raise

        try:
            return self.cf_to_python(value) if value else None
        finally:
            if value:
                self.release(value)

    def copy_attribute_bool(self, element, attribute: str) -> bool | None:
        try:
            value = self.copy_attribute(element, attribute)
        except AccessibilityError as error:
            if error.code in SOFT_ATTRIBUTE_ERROR_CODES:
                return None
            raise

        try:
            converted = self.cf_to_python(value)
            return converted if isinstance(converted, bool) else None
        finally:
            if value:
                self.release(value)

    def copy_attribute_point(self, element, attribute: str) -> dict[str, int] | None:
        return self._copy_ax_value(element, attribute, self.kAXValueCGPointType, CGPoint)

    def copy_attribute_size(self, element, attribute: str) -> dict[str, int] | None:
        return self._copy_ax_value(element, attribute, self.kAXValueCGSizeType, CGSize)

    def _copy_ax_value(self, element, attribute: str, expected_type: int, ctype):
        try:
            value = self.copy_attribute(element, attribute)
        except AccessibilityError as error:
            if error.code in SOFT_ATTRIBUTE_ERROR_CODES:
                return None
            raise

        try:
            if self.app_services.AXValueGetType(value) != expected_type:
                return None

            output = ctype()

            if not self.app_services.AXValueGetValue(
                value,
                expected_type,
                ctypes.byref(output),
            ):
                return None

            if expected_type == self.kAXValueCGPointType:
                return {"x": round(output.x), "y": round(output.y)}

            return {"width": round(output.width), "height": round(output.height)}
        finally:
            if value:
                self.release(value)

    def cf_string(self, value: str):
        created = self.core_foundation.CFStringCreateWithCString(
            None,
            value.encode("utf-8"),
            K_CFSTRING_UTF8,
        )

        if not created:
            raise AccessibilityError(
                "Impossible de creer une chaine CoreFoundation.",
                "core_foundation_error",
            )

        return created

    def cf_dictionary_get_value(self, dictionary, key: str):
        key_ref = self.cf_string(key)

        try:
            return self.core_foundation.CFDictionaryGetValue(dictionary, key_ref)
        finally:
            self.release(key_ref)

    def cf_dictionary_get_text(self, dictionary, key: str) -> str | None:
        value = self.cf_dictionary_get_value(dictionary, key)

        if not value:
            return None

        converted = self.cf_to_python(value)
        return converted if isinstance(converted, str) else None

    def cf_dictionary_get_int(self, dictionary, key: str) -> int | None:
        value = self.cf_dictionary_get_value(dictionary, key)

        if not value:
            return None

        if self.core_foundation.CFGetTypeID(value) != (
            self.core_foundation.CFNumberGetTypeID()
        ):
            return None

        output = ctypes.c_int32()

        if not self.core_foundation.CFNumberGetValue(
            value,
            K_CFNUMBER_SINT32,
            ctypes.byref(output),
        ):
            return None

        return int(output.value)

    def cf_to_python(self, value):
        type_id = self.core_foundation.CFGetTypeID(value)

        if type_id == self.core_foundation.CFStringGetTypeID():
            length = self.core_foundation.CFStringGetLength(value)
            max_size = self.core_foundation.CFStringGetMaximumSizeForEncoding(
                length,
                K_CFSTRING_UTF8,
            ) + 1
            buffer = ctypes.create_string_buffer(max_size)

            if self.core_foundation.CFStringGetCString(
                value,
                buffer,
                max_size,
                K_CFSTRING_UTF8,
            ):
                return buffer.value.decode("utf-8", errors="replace")

            return None

        if type_id == self.core_foundation.CFBooleanGetTypeID():
            return bool(self.core_foundation.CFBooleanGetValue(value))

        if type_id == self.core_foundation.CFArrayGetTypeID():
            items = []
            count = self.core_foundation.CFArrayGetCount(value)

            for index in range(count):
                item = self.core_foundation.CFArrayGetValueAtIndex(value, index)
                items.append(self.cf_to_python(item))

            return items

        return None
