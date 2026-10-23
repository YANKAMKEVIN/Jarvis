"""Local application names only; no screen capture, titles, contents or history."""
import os
from PySide6.QtCore import QObject,QTimer,Signal

class ApplicationContext(QObject):
    activated=Signal(str)
    launched=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.workspace=None;self.tokens=[]
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.poll)
    def start(self):
        try:
            from AppKit import NSWorkspace,NSWorkspaceDidLaunchApplicationNotification
            self.workspace=NSWorkspace.sharedWorkspace()
            center=self.workspace.notificationCenter()
            def launch(notification):
                app=notification.userInfo().get('NSWorkspaceApplicationKey')
                if app is None:return
                values={str(v).casefold().removesuffix('.app') for v in (app.localizedName(),app.bundleIdentifier()) if v}
                self.launched.emit(values)
            self.tokens.append(center.addObserverForName_object_queue_usingBlock_(NSWorkspaceDidLaunchApplicationNotification,None,None,launch))
            self.poll();self.timer.start()
        except (ImportError,AttributeError):self.workspace=None
    def poll(self):
        if self.workspace is None:return
        app=self.workspace.frontmostApplication()
        if app and int(app.processIdentifier())!=os.getpid():self.activated.emit(str(app.localizedName() or ''))
    def close(self):
        self.timer.stop()
        if self.workspace:
            for token in self.tokens:self.workspace.notificationCenter().removeObserver_(token)
        self.tokens.clear();self.workspace=None
