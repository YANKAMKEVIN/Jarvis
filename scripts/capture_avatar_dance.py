"""Capture actual Qt rendering at a deterministic clock; no model or microphone."""
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QSettings, QTemporaryDir
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller, DesktopShell, STYLE


def main():
    app = QApplication([])
    app.setStyleSheet(STYLE)
    temporary = QTemporaryDir()
    c = Controller(demo=True)
    shell = DesktopShell(app, c, QSettings(temporary.path()+'/dance.ini', QSettings.Format.IniFormat))
    output = Path(tempfile.mkdtemp(prefix='jarvis-dance-frames-'))
    now = [100.]
    c.dance.clock = lambda: now[0]
    try:
        shell.show_compact(); shell.finish_transfer(); app.processEvents()
        w = shell.compact
        origin = w.pos()
        c.dance.start(); c.dance.timer.stop(); w.orb.timer.stop()
        for index in range(81):
            now[0] = 100. + index / 10
            c.dance.tick()
            for _ in range(3): w.orb.tick()
            app.processEvents()
            canvas = QPixmap(420, 420); canvas.fill(QColor('#132334'))
            painter = QPainter(canvas)
            painter.setPen(QColor('#d6efff'))
            painter.drawText(15, 22, 'JARVIS · danse 2D · aperçu Qt sans micro')
            painter.drawPixmap(50+w.x()-origin.x(), 45+w.y()-origin.y(), w.grab())
            painter.end()
            assert canvas.save(str(output / f'{index:03}.png'))
        print(output)
    finally:
        c.dance.stop()
        shell.recovery.close(); shell.hold_hotkey.close(); shell.power.close()
        shell.finish_transfer()
        for widget in (shell.full, shell.compact, shell.orb_window): widget.hide()
        if shell.tray: shell.tray.hide()


if __name__ == '__main__':
    main()
