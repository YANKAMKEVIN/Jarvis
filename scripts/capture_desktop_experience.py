"""Real Qt demo captures for companion preferences, notices and routine configuration.

All stores are temporary; no microphone, model, saved user routines or actions.
QT_QPA_PLATFORM=offscreen python scripts/capture_desktop_experience.py
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import QSettings,QTemporaryDir,QPointF
from PySide6.QtGui import QPixmap,QPainter,QColor,QEnterEvent
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller,DesktopShell,STYLE
from jarvis.desktop.routines import RoutineDialog
from jarvis.macros import MacroStore


def main():
    app=QApplication([]);app.setStyleSheet(STYLE)
    temporary=QTemporaryDir();root=Path(temporary.path())
    c=Controller(demo=True);c.reduced_motion=True
    shell=DesktopShell(app,c,QSettings(str(root/'demo.ini'),QSettings.Format.IniFormat))
    output=Path(__file__).resolve().parents[1]/'docs/screenshots/experience';output.mkdir(parents=True,exist_ok=True)
    dialog=None
    def save(widget,name):
        app.processEvents()
        if not widget.grab().save(str(output/name)):raise RuntimeError(name)
    try:
        shell.show_compact();w=shell.compact
        w.set_preference('size',400)
        QApplication.sendEvent(w,QEnterEvent(QPointF(150,150),QPointF(150,150),QPointF(150,150)))
        save(w,'large-companion.png')
        w.open_menu();save(w.menu,'commands.png')
        preferences=next(a.menu() for a in w.menu.actions() if a.text()=='Personnaliser le compagnon')
        preferences.popup(w.menu.pos());save(preferences,'personalization.png')
        preferences.close();w.menu.close()
        c.notice.emit({'key':'demo-result','text':'Votre mission est terminée','mission_id':'demo'})
        app.processEvents();save(w.bubble,'mission-bubble.png')
        area=w.geometry().united(w.bubble.geometry()).adjusted(-24,-38,24,20)
        canvas=QPixmap(area.size());canvas.fill(QColor('#132334'))
        painter=QPainter(canvas);painter.setPen(QColor('#d6efff'))
        painter.drawText(12,22,'DÉMO QT · notification simulée · micro fermé')
        for widget in (w,w.bubble):painter.drawPixmap(widget.pos()-area.topLeft(),widget.grab())
        painter.end();canvas.save(str(output/'companion-notification.png'))
        w.bubble.suspend()
        store=MacroStore(root/'macros.db');store.save('Ma journée','Lis mon agenda et mes rappels du jour, puis résume mes priorités. Ne modifie et n’envoie rien.')
        dialog=RoutineDialog(c,store=store);dialog.show();dialog.list.setCurrentRow(0)
        save(dialog,'routine-configuration.png')
    finally:
        if dialog:dialog.close();dialog.deleteLater()
        shell.recovery.close();shell.hold_hotkey.close();shell.power.close()
        shell.finish_transfer()
        for widget in (shell.full,shell.compact,shell.orb_window):widget.hide()
        if shell.tray:shell.tray.hide()
    print(output)

if __name__=='__main__':main()
