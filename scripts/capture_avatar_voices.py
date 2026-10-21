"""Capture the real voice settings dialog with isolated preferences; no microphone."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QSettings, QTemporaryDir
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller, DesktopShell, STYLE


def main():
    app = QApplication([])
    app.setStyleSheet(STYLE)
    temporary = QTemporaryDir()
    controller = Controller(demo=True)
    controller.reduced_motion = True
    shell = DesktopShell(app, controller, QSettings(temporary.path()+'/voices.ini', QSettings.Format.IniFormat))
    output = Path(__file__).resolve().parents[1] / 'docs/screenshots/experience/avatar-voices.png'
    try:
        shell.show_voices()
        shell.voice_dialog.follow_avatar('neo_guide')
        shell.voice_dialog.voices.setCurrentIndex(shell.voice_dialog.voices.findData('Kore'))
        app.processEvents()
        assert shell.voice_dialog.grab().save(str(output))
        print(output)
    finally:
        if shell.voice_dialog: shell.voice_dialog.close(); shell.voice_dialog.deleteLater()
        shell.recovery.close(); shell.hold_hotkey.close(); shell.power.close(); shell.finish_transfer()
        for widget in (shell.full, shell.compact, shell.orb_window): widget.hide()
        if shell.tray: shell.tray.hide()


if __name__ == '__main__':
    main()
