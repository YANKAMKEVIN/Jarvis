"""ApplicationServices (AX) backend: the only code that talks to the macOS Accessibility API."""
from __future__ import annotations

import ctypes
from ctypes import util

from jarvis.tools.accessibility_common import (
    AX_ERROR_CODES,
    AccessibilityError,
)
from jarvis.tools.accessibility_windows import AXWindowsMixin
from jarvis.tools.accessibility_elements import AXElementsMixin
from jarvis.tools.accessibility_attributes import AXAttributesMixin


class ApplicationServicesAccessibilityBackend(
    AXWindowsMixin,
    AXElementsMixin,
    AXAttributesMixin,
):
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

    def create_application(self, pid: int):
        return self.app_services.AXUIElementCreateApplication(int(pid))

    def ensure_trusted(self) -> None:
        if not self.is_trusted():
            raise AccessibilityError(
                (
                    "Jarvis a besoin de l'autorisation Accessibility macOS "
                    "pour inspecter l'interface."
                ),
                "accessibility_permission_error",
            )

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
