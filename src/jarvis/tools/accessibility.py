from __future__ import annotations

import ctypes
import unicodedata
from ctypes import util
from dataclasses import dataclass
from typing import Any


DEFAULT_UI_MAX_DEPTH = 4
DEFAULT_UI_MAX_ELEMENTS = 80
MAX_UI_DEPTH = 6
MAX_UI_ELEMENTS = 150
VALUE_SUMMARY_MAX_CHARS = 80
K_CFSTRING_UTF8 = 0x08000100
K_CFNUMBER_SINT32 = 3
K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY = 1
K_CG_WINDOW_LIST_EXCLUDE_DESKTOP_ELEMENTS = 16
K_CG_NULL_WINDOW_ID = 0

SYSTEM_WINDOW_OWNERS = {
    "Window Server",
    "Dock",
    "Control Center",
    "SystemUIServer",
    "NotificationCenter",
    "Spotlight",
    "CoreServicesUIAgent",
    "Outil de signalement de problème",
    "Problem Reporter",
}

INTERESTING_ROLES = {
    "AXButton",
    "AXTextField",
    "AXSecureTextField",
    "AXTextArea",
    "AXSearchField",
    "AXCheckBox",
    "AXRadioButton",
    "AXPopUpButton",
    "AXMenuItem",
    "AXLink",
    "AXTab",
    "AXStaticText",
}

TEXT_ROLES = {"AXTextField", "AXTextArea", "AXSecureTextField", "AXSearchField"}
SECURE_ROLES = {"AXSecureTextField"}

# Reading an OPTIONAL element attribute can fail for reasons that mean "this
# attribute is not readable on this element" rather than "the element itself is
# invalid". Those degrade to None so a single unreadable attribute never drops
# the whole element from a snapshot. Observed in the field: TextEdit's main
# AXTextArea raises kAXErrorFailure (-25200) on an optional attribute, which
# previously discarded the only editable target. Hard errors not listed here
# (e.g. invalid_ui_element) still propagate.
SOFT_ATTRIBUTE_ERROR_CODES = {
    "attribute_unsupported",
    "no_value",
    "failure",
    "cannot_complete",
}

AX_ERROR_CODES = {
    0: "success",
    -25200: "failure",
    -25201: "illegal_argument",
    -25202: "invalid_ui_element",
    -25203: "invalid_ui_element_observer",
    -25204: "cannot_complete",
    -25205: "attribute_unsupported",
    -25206: "action_unsupported",
    -25207: "notification_unsupported",
    -25208: "not_implemented",
    -25209: "notification_already_registered",
    -25210: "notification_not_registered",
    -25211: "api_disabled",
    -25212: "no_value",
    -25213: "parameterized_attribute_unsupported",
    -25214: "not_enough_precision",
}


class AccessibilityError(Exception):
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


class CFRange(ctypes.Structure):
    _fields_ = [
        ("location", ctypes.c_long),
        ("length", ctypes.c_long),
    ]


class ApplicationServicesAccessibilityBackend:
    kAXValueCGPointType = 1
    kAXValueCGSizeType = 2

    def __init__(self, app_services=None, core_foundation=None, core_graphics=None):
        self.app_services = (
            app_services
            if app_services is not None
            else self._load_framework("ApplicationServices")
        )
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
            raise AccessibilityError(
                f"Le framework macOS {name} est indisponible.",
                "framework_missing",
            )

        return ctypes.CDLL(path)

    def _configure_signatures(self) -> None:
        ax = self.app_services
        cg = self.core_graphics
        cf = self.core_foundation

        ax.AXIsProcessTrusted.argtypes = []
        ax.AXIsProcessTrusted.restype = ctypes.c_bool
        ax.AXUIElementCreateSystemWide.argtypes = []
        ax.AXUIElementCreateSystemWide.restype = ctypes.c_void_p
        ax.AXUIElementCreateApplication.argtypes = [ctypes.c_int32]
        ax.AXUIElementCreateApplication.restype = ctypes.c_void_p
        ax.AXUIElementCopyAttributeValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ax.AXUIElementCopyAttributeValue.restype = ctypes.c_int32
        ax.AXUIElementCopyActionNames.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ax.AXUIElementCopyActionNames.restype = ctypes.c_int32
        ax.AXUIElementPerformAction.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        ax.AXUIElementPerformAction.restype = ctypes.c_int32
        ax.AXUIElementSetAttributeValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        ax.AXUIElementSetAttributeValue.restype = ctypes.c_int32
        ax.AXUIElementIsAttributeSettable.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_bool),
        ]
        ax.AXUIElementIsAttributeSettable.restype = ctypes.c_int32
        ax.AXValueGetType.argtypes = [ctypes.c_void_p]
        ax.AXValueGetType.restype = ctypes.c_int32
        ax.AXValueGetValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int32,
            ctypes.c_void_p,
        ]
        ax.AXValueGetValue.restype = ctypes.c_bool

        cg.CGWindowListCopyWindowInfo.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
        ]
        cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p

        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        cf.CFRetain.argtypes = [ctypes.c_void_p]
        cf.CFRetain.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringGetLength.argtypes = [ctypes.c_void_p]
        cf.CFStringGetLength.restype = ctypes.c_long
        cf.CFStringGetMaximumSizeForEncoding.argtypes = [
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        cf.CFStringGetMaximumSizeForEncoding.restype = ctypes.c_long
        cf.CFStringGetCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        cf.CFArrayGetCount.restype = ctypes.c_long
        cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFDictionaryGetValue.restype = ctypes.c_void_p
        cf.CFNumberGetValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int32,
            ctypes.c_void_p,
        ]
        cf.CFNumberGetValue.restype = ctypes.c_bool
        cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
        cf.CFBooleanGetValue.restype = ctypes.c_bool
        cf.CFGetTypeID.argtypes = [ctypes.c_void_p]
        cf.CFGetTypeID.restype = ctypes.c_ulong
        cf.CFStringGetTypeID.argtypes = []
        cf.CFStringGetTypeID.restype = ctypes.c_ulong
        cf.CFNumberGetTypeID.argtypes = []
        cf.CFNumberGetTypeID.restype = ctypes.c_ulong
        cf.CFDictionaryGetTypeID.argtypes = []
        cf.CFDictionaryGetTypeID.restype = ctypes.c_ulong
        cf.CFBooleanGetTypeID.argtypes = []
        cf.CFBooleanGetTypeID.restype = ctypes.c_ulong
        cf.CFArrayGetTypeID.argtypes = []
        cf.CFArrayGetTypeID.restype = ctypes.c_ulong

        self._cf_true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")

    def is_trusted(self) -> bool:
        return bool(self.app_services.AXIsProcessTrusted())

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

    def create_application(self, pid: int):
        return self.app_services.AXUIElementCreateApplication(int(pid))

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

    def ensure_trusted(self) -> None:
        if not self.is_trusted():
            raise AccessibilityError(
                (
                    "Jarvis a besoin de l'autorisation Accessibility macOS "
                    "pour inspecter l'interface."
                ),
                "accessibility_permission_error",
            )

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

    def release(self, value) -> None:
        if value:
            self.core_foundation.CFRelease(value)

    def retain(self, value):
        if not value:
            return value

        return self.core_foundation.CFRetain(value)

    @staticmethod
    def status_code(status: int) -> str:
        return AX_ERROR_CODES.get(status, f"ax_error_{status}")

    def raise_for_status(self, status: int, context: str) -> None:
        if status == 0:
            return

        code = self.status_code(status)

        if code == "api_disabled":
            raise AccessibilityError(
                "L'API Accessibility macOS est desactivee ou non autorisee.",
                "accessibility_permission_error",
                {"context": context},
            )

        raise AccessibilityError(
            f"Erreur Accessibility pendant {context}: {code}.",
            code,
            {"context": context},
        )


@dataclass
class AccessibilityTools:
    backend: Any | None = None

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = ApplicationServicesAccessibilityBackend()

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


def strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise AccessibilityError(
            "La recherche d'element UI ne peut pas etre vide.",
            "invalid_ui_query",
        )

    return normalize_text(query)


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""

    value = unicodedata.normalize("NFD", value.casefold().strip())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return " ".join(value.split())


def searchable_fields(element: dict[str, Any]) -> list[str]:
    return [
        item
        for item in (
            element.get("title"),
            element.get("description"),
            element.get("identifier"),
        )
        if isinstance(item, str) and item.strip()
    ]


def match_elements(
    elements: list[dict[str, Any]],
    normalized_query: str,
    normalized_role: str | None,
) -> list[dict[str, Any]]:
    role_filtered = [
        element
        for element in elements
        if not normalized_role or normalize_text(element.get("role")) == normalized_role
    ]
    exact_matches = [
        element
        for element in role_filtered
        if normalized_query in {normalize_text(field) for field in searchable_fields(element)}
    ]

    if exact_matches:
        return exact_matches

    if is_short_exact_query(normalized_query):
        return []

    return [
        element
        for element in role_filtered
        if any(normalized_query in normalize_text(field) for field in searchable_fields(element))
    ]


def is_short_exact_query(normalized_query: str) -> bool:
    return len(normalized_query) == 1


def should_include_element(element: dict[str, Any]) -> bool:
    role = element.get("role")

    if role not in INTERESTING_ROLES and not element.get("actions"):
        return False

    if role == "AXStaticText" and not element.get("title") and not element.get("description"):
        return False

    return True


def compact_element(element: dict[str, Any]) -> dict[str, Any]:
    if element.get("secure"):
        element["value_summary"] = None

    return {
        key: value
        for key, value in element.items()
        if value is not None and value != []
    }


def strip_handle(element: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in element.items()
        if key != "_handle"
    }


def strip_handles(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [strip_handle(item) for item in elements]
