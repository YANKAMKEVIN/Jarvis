"""Non-activating temporary bubble attached to the existing companion."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame,QHBoxLayout,QPushButton
from jarvis.desktop.notifications import NoticeQueue

class NoticeBubble(QFrame):
    def __init__(self, companion):
        super().__init__(companion,Qt.WindowType.ToolTip|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.companion=companion
        self.queue=NoticeQueue()
        self.current=None
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet('QFrame { background:#13283b; border:1px solid #5d8ba7; border-radius:12px; } QPushButton { background:transparent; color:#e3f5ff; border:0; padding:10px; text-align:left; }')
        row=QHBoxLayout(self);row.setContentsMargins(4,4,4,4)
        self.open=QPushButton();self.open.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open.clicked.connect(self.activate_notice);row.addWidget(self.open)
        close=QPushButton('×');close.setAccessibleName('Fermer la notification');close.setFixedWidth(28)
        close.clicked.connect(self.dismiss);row.addWidget(close)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(7000);self.timer.timeout.connect(self.dismiss)
    def enqueue(self,event):
        if not self.companion.preferences.bubbles: return
        if self.queue.put(**event):
            self.companion.wake_companion();self.present_next()
    def present_next(self):
        if self.current or not self.companion.isVisible() or not self.companion.preferences.bubbles: return
        self.current=self.queue.take()
        if self.current is None: return
        import textwrap
        self.open.setText('\n'.join(textwrap.wrap(self.current.text,36)))
        self.open.setAccessibleName(self.current.text+' · ouvrir les détails')
        self.adjustSize();self.reposition();self.show();self.timer.start()
        from jarvis.desktop.macos_spaces import join_all_spaces
        join_all_spaces(self)
    def reposition(self):
        if not self.current: return
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication
        area=(QGuiApplication.screenAt(self.companion.geometry().center()) or self.companion.screen()).availableGeometry()
        p=self.companion.mapToGlobal(QPoint(0,0))
        self.move(max(area.left(),min(p.x(),area.right()-self.width()+1)),
                  max(area.top(),min(p.y()-self.height()-8,area.bottom()-self.height()+1)))
    def dismiss(self):
        self.timer.stop();self.current=None;self.hide();self.present_next()
    def suspend(self):
        self.timer.stop();self.current=None;self.hide()
    def activate_notice(self):
        notice=self.current
        self.suspend()
        if not notice: return
        shell=self.companion.shell
        if notice.mission_id: shell.controller.select_mission(notice.mission_id)
        if notice.destination=='undo':shell.experience.undo()
        elif notice.destination=='history':shell.experience.history()
        elif notice.destination=='experience':shell.experience.open()
        elif notice.destination=='settings': shell.show_settings()
        elif notice.destination=='details': shell.show_details()
        else: shell.show_mission_details()
