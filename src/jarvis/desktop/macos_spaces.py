"""Native Spaces behavior for floating avatar windows only.

Qt's always-on-top flag controls stacking, not which macOS Space owns a window.
Joining every Space is not enough for another app's full-screen Space: macOS
only admits a non-activating panel there. Floating windows are therefore Qt
tool windows (an NSPanel on Cocoa) turned into non-activating panels that stay
visible when Jarvis is not the active app.
QWidget.winId() is an NSView pointer on the Cocoa platform; keep this bridge
strictly behind that platform check so offscreen test handles are never cast.
"""
import ctypes
import logging
import sys
from PySide6.QtCore import Qt
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


def floating_window_type():
    """A tool window becomes an NSPanel on macOS, the only kind shown over full screen."""
    return Qt.WindowType.Tool if sys.platform == 'darwin' else Qt.WindowType.Window


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
        if window.isKindOfClass_(AppKit.NSPanel):
            frame = window.frame()  # changing the style mask may move the panel
            window.setStyleMask_(window.styleMask() | AppKit.NSWindowStyleMaskNonactivatingPanel)
            window.setHidesOnDeactivate_(False)
            window.setFrame_display_(frame, False)
        behavior = floating_collection_behavior(window.collectionBehavior(), AppKit)
        window.setCollectionBehavior_(behavior)
        return int(window.collectionBehavior()) == behavior
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError) as error:
        log.warning('Compagnon : affichage sur tous les bureaux indisponible : %s', error)
        return False
