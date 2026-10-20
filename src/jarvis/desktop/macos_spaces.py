"""Native Spaces behavior for floating avatar windows only.

Qt's always-on-top flag controls stacking, not which macOS Space owns a window.
QWidget.winId() is an NSView pointer on the Cocoa platform; keep this bridge
strictly behind that platform check so offscreen test handles are never cast.
"""
import ctypes
import logging
import sys
from PySide6.QtGui import QGuiApplication

log = logging.getLogger(__name__)


def floating_collection_behavior(current, appkit):
    """Preserve unrelated Cocoa flags while replacing conflicting Space modes."""
    excluded = (appkit.NSWindowCollectionBehaviorMoveToActiveSpace |
                appkit.NSWindowCollectionBehaviorFullScreenPrimary |
                appkit.NSWindowCollectionBehaviorFullScreenNone)
    return ((int(current) & ~excluded) |
            appkit.NSWindowCollectionBehaviorCanJoinAllSpaces |
            appkit.NSWindowCollectionBehaviorFullScreenAuxiliary)


def join_all_spaces(widget):
    """Apply to an existing native view, on the Qt GUI thread. No window activation."""
    if sys.platform != 'darwin' or QGuiApplication.platformName() != 'cocoa':
        return False
    try:
        import AppKit
        import objc
        view = objc.objc_object(c_void_p=ctypes.c_void_p(int(widget.winId())))
        window = view.window()
        if window is None:
            return False
        behavior = floating_collection_behavior(window.collectionBehavior(), AppKit)
        window.setCollectionBehavior_(behavior)
        return int(window.collectionBehavior()) == behavior
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as error:
        log.warning('Compagnon : affichage sur tous les bureaux indisponible : %s', error)
        return False
