"""Spaces bridge: preserve flags, never cast a non-Cocoa window handle."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from jarvis.desktop import macos_spaces

FLAGS = SimpleNamespace(
    NSWindowCollectionBehaviorCanJoinAllSpaces=1,
    NSWindowCollectionBehaviorMoveToActiveSpace=2,
    NSWindowCollectionBehaviorFullScreenPrimary=128,
    NSWindowCollectionBehaviorFullScreenAuxiliary=256,
    NSWindowCollectionBehaviorFullScreenNone=512,
    NSPanel=object(),
    NSWindowStyleMaskNonactivatingPanel=128,
)


def test_spaces_flags_preserve_other_behaviors_and_are_idempotent():
    original = 2 | 128 | 512 | 16 | 64
    value = macos_spaces.floating_collection_behavior(original, FLAGS)
    assert value == 1 | 256 | 16 | 64
    assert macos_spaces.floating_collection_behavior(value, FLAGS) == value


def test_offscreen_and_non_macos_never_access_native_handle(monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = Mock()
    for platform in ('darwin', 'linux'):
        monkeypatch.setattr(macos_spaces.sys,'platform',platform)
        assert macos_spaces.join_all_spaces(widget) is False
        widget.winId.assert_not_called()


def test_cocoa_bridge_resolves_nsview_and_applies_to_its_window(monkeypatch):
    import sys
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(macos_spaces.sys,'platform','darwin')
    monkeypatch.setattr(macos_spaces.QGuiApplication,'platformName',lambda:'cocoa')
    native = Mock()
    native.collectionBehavior.side_effect = [2|128|16,1|256|16]
    native.isKindOfClass_.return_value = True
    native.styleMask.return_value = 1
    bridge = Mock(return_value=SimpleNamespace(window=lambda:native))
    monkeypatch.setitem(sys.modules,'objc',SimpleNamespace(objc_object=bridge))
    monkeypatch.setitem(sys.modules,'AppKit',FLAGS)
    widget = Mock()
    widget.winId.return_value = 1234
    assert macos_spaces.join_all_spaces(widget)
    assert bridge.call_args.kwargs['c_void_p'].value == 1234
    native.setCollectionBehavior_.assert_called_once_with(1|256|16)
    # A panel becomes non-activating, survives deactivation and keeps its frame.
    native.isKindOfClass_.assert_called_once_with(FLAGS.NSPanel)
    native.setStyleMask_.assert_called_once_with(1|128)
    native.setHidesOnDeactivate_.assert_called_once_with(False)
    native.setFrame_display_.assert_called_once_with(native.frame.return_value, False)


def test_plain_windows_keep_their_style(monkeypatch):
    import sys
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(macos_spaces.sys,'platform','darwin')
    monkeypatch.setattr(macos_spaces.QGuiApplication,'platformName',lambda:'cocoa')
    native = Mock()
    native.collectionBehavior.side_effect = [0,1|256]
    native.isKindOfClass_.return_value = False
    monkeypatch.setitem(sys.modules,'objc',SimpleNamespace(objc_object=lambda **kw:SimpleNamespace(window=lambda:native)))
    monkeypatch.setitem(sys.modules,'AppKit',FLAGS)
    widget = Mock()
    widget.winId.return_value = 1234
    assert macos_spaces.join_all_spaces(widget)
    native.setStyleMask_.assert_not_called()


def test_floating_windows_are_tool_windows_on_macos(monkeypatch):
    from PySide6.QtCore import Qt
    monkeypatch.setattr(macos_spaces.sys,'platform','darwin')
    assert macos_spaces.floating_window_type() == Qt.WindowType.Tool
    monkeypatch.setattr(macos_spaces.sys,'platform','linux')
    assert macos_spaces.floating_window_type() == Qt.WindowType.Window


def test_missing_native_window_is_safe(monkeypatch):
    import sys
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(macos_spaces.sys,'platform','darwin')
    monkeypatch.setattr(macos_spaces.QGuiApplication,'platformName',lambda:'cocoa')
    monkeypatch.setitem(sys.modules,'objc',SimpleNamespace(objc_object=lambda **kw:SimpleNamespace(window=lambda:None)))
    monkeypatch.setitem(sys.modules,'AppKit',FLAGS)
    widget = Mock()
    widget.winId.return_value = 1234
    assert not macos_spaces.join_all_spaces(widget)


def test_only_floating_modes_apply_spaces_behavior_on_each_show(monkeypatch):
    from PySide6.QtCore import QSettings, QTemporaryDir
    from jarvis.desktop.app import Controller, DesktopShell
    app = QApplication.instance() or QApplication([])
    temporary = QTemporaryDir()
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable',lambda:False)
    apply = Mock(return_value=True)
    monkeypatch.setattr(macos_spaces,'join_all_spaces',apply)
    c = Controller(demo=True)
    c.reduced_motion=True
    shell = DesktopShell(app,c,QSettings(temporary.path()+'/settings.ini',QSettings.Format.IniFormat))
    try:
        shell.show_full()
        apply.assert_not_called()
        shell.show_compact()
        shell.show_orb()
        shell.show_compact()
        assert [call.args[0] for call in apply.call_args_list] == [shell.compact,shell.orb_window,shell.compact]
        assert c.voice_worker is None
    finally:
        for window in (shell.full,shell.compact,shell.orb_window): window.hide()
