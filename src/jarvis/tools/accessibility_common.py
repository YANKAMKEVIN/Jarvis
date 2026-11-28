"""Shared constants, errors, ctypes structures and pure helpers of the Accessibility layer."""
from __future__ import annotations

import ctypes
import unicodedata
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
