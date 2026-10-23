"""Real Qt captures with temporary stores. No microphone, model or native capture."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import QSettings,QTemporaryDir,Qt
from PySide6.QtGui import QColor,QPainter,QPixmap
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller,DesktopShell,STYLE
from jarvis.desktop.visuals import Orb
from jarvis.desktop.articulated_avatar import RIG_IDS
from jarvis.desktop.appearances import BY_ID


def main():
    app=QApplication([]);app.setStyleSheet(STYLE)
    temp=QTemporaryDir();root=Path(temp.path())
    for key,name in [('JARVIS_MACROS_PATH','macros'),('JARVIS_MEMORY_PATH','memory'),('JARVIS_CONTEXT_PATH','context')]:os.environ[key]=str(root/(name+'.db'))
    c=Controller(demo=True);c.reduced_motion=True
    shell=DesktopShell(app,c,QSettings(str(root/'ui.ini'),QSettings.Format.IniFormat));e=shell.experience
    output=Path(__file__).resolve().parents[1]/'docs/screenshots/twenty';output.mkdir(parents=True,exist_ok=True)
    def save(widget,name):app.processEvents();assert widget.grab().save(str(output/name))
    orbs=[]
    try:
        shell.show_compact();shell.finish_transfer()
        palette=e.palette();save(palette,'commands.png');palette.close()
        cockpit=e.open();save(cockpit,'daily-cockpit.png')
        from PySide6.QtWidgets import QTabWidget
        cockpit.findChild(QTabWidget).setCurrentIndex(1);save(cockpit,'preferences.png')
        e.set_option('theme','contrast');save(cockpit,'high-contrast.png');e.set_option('theme','night');cockpit.close()
        e.set_option('articulated',True)
        canvas=QPixmap(1200,360);canvas.fill(QColor('#0d1c2b'));painter=QPainter(canvas);painter.setPen(QColor('#dce8f6'))
        for index,appearance in enumerate(sorted(RIG_IDS)):
            orb=Orb(240);orb.appearance=appearance;orb.articulated=True;orb.set_motion(False);orb.show();app.processEvents();orbs.append(orb)
            painter.drawPixmap(index*240,25,orb.grab());painter.drawText(index*240+22,325,BY_ID[appearance].name)
        painter.drawText(20,18,'JARVIS · HUMANOÏDES ARTICULÉS · STYLE DESSINÉ 2D · CAPTURE QT')
        painter.end();canvas.save(str(output/'articulated-humanoids.png'))
        print(output)
    finally:
        for orb in orbs:orb.hide();orb.deleteLater()
        e.close();shell.recovery.close();shell.hold_hotkey.close();shell.power.close();shell.finish_transfer()
        for window in (shell.full,shell.compact,shell.orb_window):window.hide()
        if shell.tray:shell.tray.hide()


if __name__=='__main__':main()
