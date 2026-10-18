"""Capture the real Qt menu in demo mode, without native tray or microphone.

QT_QPA_PLATFORM=offscreen python scripts/capture_desktop_menu.py
The macOS native menu will use the system appearance instead.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    from PySide6.QtWidgets import QApplication
    from jarvis.desktop.app import Controller, DesktopShell, STYLE
    from jarvis.desktop.tray import TrayControls

    class Settings:
        def value(self, key, default=None): return default
        def setValue(self, key, value): pass

    class PreviewTray:
        def setContextMenu(self, menu): pass
        def setToolTip(self, text): pass
        def setIcon(self, icon): pass

    app = QApplication([])
    app.setStyleSheet(STYLE)
    controller = Controller(demo=True)
    shell = DesktopShell(app, controller, Settings())
    controls = TrayControls(shell, PreviewTray())
    target = ROOT / 'docs/screenshots/menu-controls.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        controls.menu.show()
        app.processEvents()
        if not controls.menu.grab().save(str(target)):
            raise RuntimeError('Cannot save menu screenshot')
    finally:
        controls.menu.hide()
        if shell.tray:
            shell.tray.hide()
    print(target)


if __name__ == '__main__':
    main()
