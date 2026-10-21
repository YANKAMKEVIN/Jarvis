"""Exercise companion presentation, Spaces, power observers and hold-key registration.

No microphone, Gemini session, system action or user settings are opened.
python scripts/diagnose_desktop_experience.py --native  # macOS WindowServer
python scripts/diagnose_desktop_experience.py           # offscreen widgets
"""
import argparse
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true');args=parser.parse_args()
    if args.native and sys.platform!='darwin':parser.error('--native nécessite macOS')
    os.environ['QT_QPA_PLATFORM']='cocoa' if args.native else 'offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings,QTemporaryDir,QCoreApplication,QEvent
    from jarvis.desktop.app import Controller,DesktopShell
    from jarvis.desktop.hotkey import HoldHotkey
    app=QApplication([]);temporary=QTemporaryDir()
    c=Controller(demo=True);c.reduced_motion=True
    shell=DesktopShell(app,c,QSettings(temporary.path()+'/demo.ini',QSettings.Format.IniFormat))
    hold=HoldHotkey(lambda:None,lambda:None,platform='darwin',demo=not args.native)
    try:
        shell.show_compact();app.processEvents()
        w=shell.compact
        w.set_preference('size',400);w.set_preference('opacity',.85);w.set_preference('anchor','bottom_right')
        app.processEvents()
        assert w.orb.width()==400 and w.screen().availableGeometry().contains(w.geometry())
        w.screen().availableGeometryChanged.emit(w.screen().availableGeometry())
        c.notice.emit({'key':'native-demo','text':'Exemple · votre mission est terminée','destination':'missions'})
        app.processEvents();assert w.bubble.isVisible()
        if args.native:
            import ctypes,AppKit,objc
            shell.power.start();assert len(shell.power.tokens)==2
            hold.set_enabled(True);print('Raccourci natif :',hold.message)
            for widget in (w,w.bubble):
                native=objc.objc_object(c_void_p=ctypes.c_void_p(int(widget.winId()))).window()
                assert native.collectionBehavior() & AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        assert c.voice_worker is None
        print('Compagnon, personnalisation et bulle : OK. Aucun micro ouvert.')
    finally:
        hold.close();shell.power.close();shell.recovery.close()
        for widget in (shell.full,shell.compact,shell.orb_window):widget.hide();widget.deleteLater()
        if shell.tray:shell.tray.hide()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

if __name__=='__main__':main()
