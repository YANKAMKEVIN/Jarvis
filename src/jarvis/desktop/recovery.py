"""Bounded voice recovery; never replays missions or overlaps voice workers."""
from PySide6.QtCore import QObject,QTimer,Signal

READY={'listening','muted','speaking','thinking'}

class VoiceRecovery(QObject):
    def __init__(self,controller,enabled=True):
        super().__init__(controller)
        self.c=controller;self.enabled=enabled;self.attempts=0
        self.sleeping=False;self.pending_wake=False;self.closed=False;self.handling=False
        self.restored_notified=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.retry)
        self.stable=QTimer(self);self.stable.setSingleShot(True);self.stable.setInterval(10000);self.stable.timeout.connect(self.mark_stable)
        controller.changed.connect(self.observe)
    def set_enabled(self,enabled):
        self.enabled=bool(enabled)
        if not enabled:self.timer.stop();self.set_message('')
        self.observe()
    def set_message(self,message):
        if self.c.recovery_message!=message:
            self.c.recovery_message=message;self.c.changed.emit()
    def observe(self):
        if self.handling:return
        self.handling=True
        try:
            c=self.c
            if self.closed or not self.enabled or self.sleeping or not c.voice_desired or c.user_stop_requested or c.quit_after_voice:
                self.timer.stop();self.stable.stop()
                if not c.voice_desired or c.user_stop_requested:
                    self.pending_wake=False;self.set_message('')
                return
            if c.voice_state in READY and c.voice_worker and not self.pending_wake:
                self.timer.stop()
                if self.attempts and not self.restored_notified:
                    self.restored_notified=True
                    c.notice.emit({'key':f'recovered:{self.attempts}:{id(c.voice_worker)}','text':'Connexion rétablie · aucune mission relancée','destination':'details'})
                if not self.stable.isActive():self.stable.start()
                self.set_message('');return
            self.stable.stop()
            if c.voice_state=='error':
                c.end_push_to_talk();self.restored_notified=False
            if c.voice_worker is not None or c.audio_worker is not None:return
            eligible=self.pending_wake or (c.voice_state=='error' and c.can_reconnect)
            if not eligible:return
            if self.attempts>=3:
                self.set_message('Reconnexion interrompue après 3 essais · réessayez depuis le menu.');return
            if not self.timer.isActive():
                delay=(2000,5000,10000)[self.attempts]
                self.set_message(f'Reconnexion dans {delay//1000} s · essai {self.attempts+1}/3')
                self.timer.start(delay)
        finally:self.handling=False
    def retry(self):
        c=self.c
        if self.closed or self.sleeping or not self.enabled or not c.voice_desired or c.user_stop_requested or c.quit_after_voice:return
        if c.voice_worker is not None or c.audio_worker is not None:
            self.observe();return
        self.attempts+=1;self.pending_wake=False
        c.microphone_muted=c.microphone_muted or c.ptt_enabled
        c.start_voice(reconnect=True,_automatic=True)
    def manual_start(self):
        self.timer.stop();self.stable.stop();self.attempts=0;self.restored_notified=False;self.pending_wake=False
    def mark_stable(self):
        if self.c.voice_worker and self.c.voice_state in READY:self.attempts=0
    def before_sleep(self):
        self.sleeping=True;self.timer.stop();self.stable.stop()
        c=self.c;c.end_push_to_talk()
        if c.voice_worker:
            c.voice_worker.set_muted(True);c.voice_worker.stop()
            c.voice_state='stopping';c.changed.emit()
    def after_wake(self):
        self.sleeping=False
        c=self.c
        if c.voice_desired and not c.user_stop_requested:
            self.pending_wake=True;c.can_reconnect=True
            if c.voice_worker:c.voice_worker.stop()
            else:c.voice_state='error'
            c.notice.emit({'key':'wake:voice','text':'Réveil du Mac · récupération du vocal','destination':'settings'})
            c.changed.emit();self.observe()
    def close(self):
        self.closed=True;self.timer.stop();self.stable.stop()


class MacPowerMonitor(QObject):
    sleeping=Signal()
    waking=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.center=None;self.tokens=[]
    def start(self):
        import sys
        from PySide6.QtGui import QGuiApplication
        if sys.platform!='darwin' or QGuiApplication.platformName()!='cocoa':return
        try:
            import AppKit,Foundation
            self.center=AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
            for name,signal in ((AppKit.NSWorkspaceWillSleepNotification,self.sleeping),(AppKit.NSWorkspaceDidWakeNotification,self.waking)):
                self.tokens.append(self.center.addObserverForName_object_queue_usingBlock_(name,None,Foundation.NSOperationQueue.mainQueue(),lambda note,s=signal:s.emit()))
        except (ImportError,AttributeError,RuntimeError):self.close()
    def close(self):
        if self.center:
            for token in self.tokens:self.center.removeObserver_(token)
        self.tokens=[];self.center=None
