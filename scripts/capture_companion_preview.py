"""Capture the real transparent compact companion, with isolated demo settings.

QT_QPA_PLATFORM=offscreen python scripts/capture_companion_preview.py
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import QEvent, QPointF, QSettings, QTemporaryDir
from PySide6.QtGui import QEnterEvent, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller, DesktopShell, STYLE


def main():
    app = QApplication([])
    app.setStyleSheet(STYLE)
    temporary = QTemporaryDir()
    c = Controller(demo=True)
    c.reduced_motion = True
    shell = DesktopShell(app,c,QSettings(temporary.path()+'/demo.ini',QSettings.Format.IniFormat))
    output = Path(__file__).resolve().parents[1]/'docs/screenshots/avatars'
    output.mkdir(parents=True,exist_ok=True)
    def save(name):
        app.processEvents()
        if not shell.compact.grab().save(str(output/name)):
            raise RuntimeError(name)
    try:
        shell.show_compact()
        app.processEvents()
        shell.compact.conceal_controls()
        save('companion-avatar.png')
        idle = shell.compact.grab()
        QApplication.sendEvent(shell.compact,QEnterEvent(QPointF(160,160),QPointF(160,160),QPointF(160,160)))
        save('companion-hover.png')
        hovered = shell.compact.grab()
        # A labelled backing canvas makes the actual capture's transparency
        # readable in viewers that otherwise ignore PNG alpha.
        canvas = QPixmap(720,410)
        canvas.fill(QColor('#132334'))
        painter = QPainter(canvas)
        painter.setPen(QColor('#cde8f5'))
        painter.drawText(28,30,'AU REPOS')
        painter.drawText(388,30,'AU SURVOL · 2 COMMANDES')
        painter.drawPixmap(20,48,idle)
        painter.drawPixmap(380,48,hovered)
        painter.end()
        if not canvas.save(str(output/'companion-comparison.png')):
            raise RuntimeError('Could not save comparison')
        shell.set_appearance('orbital_atlas')
        shell.compact.conceal_controls()
        save('companion-abstract.png')
    finally:
        shell.finish_transfer()
        for widget in (shell.full,shell.compact,shell.orb_window):
            widget.hide()
        if shell.tray: shell.tray.hide()
    print(output)

if __name__=='__main__':
    main()
