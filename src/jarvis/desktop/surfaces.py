"""Desktop glass surface, discoverable controls and an orb transfer animation."""
from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsOpacityEffect, QLabel, QPushButton, QWidget


class GlassSurface(QWidget):
    """Translucent painted glass; does not claim native macOS backdrop blur."""
    def paintEvent(self, event):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = self.rect().adjusted(10, 10, -10, -10)
        p.setPen(Qt.PenStyle.NoPen)
        for spread in range(9, 0, -1):
            p.setBrush(QColor(0, 3, 10, 3))
            p.drawRoundedRect(box.adjusted(-spread, -spread, spread, spread), 30, 30)
        glass = QLinearGradient(box.topLeft(), box.bottomRight())
        glass.setColorAt(0, QColor(25, 43, 59, 246))
        glass.setColorAt(0.55, QColor(11, 22, 35, 242))
        glass.setColorAt(1, QColor(8, 15, 26, 249))
        p.setBrush(glass)
        p.setPen(QPen(QColor(145, 204, 234, 54), 1))
        p.drawRoundedRect(box, 26, 26)
        p.setPen(QPen(QColor(201, 236, 255, 70), 1))
        p.drawLine(box.left() + 28, box.top() + 1, box.right() - 28, box.top() + 1)
        p.end()


class DragHandle(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName('eyebrow')
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip('Déplacer le compagnon')
        self.origin = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.globalPosition().toPoint() - self.window().pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self.origin)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.origin is not None:
            self.origin = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.window().shell.remember_companion()
            event.accept()


class NavButton(QPushButton):
    """Sidebar entry: line icon on the left; counter, live dot or shortcut on the right."""
    def __init__(self, text, kind, shortcut=''):
        super().__init__(text)
        self.kind, self.shortcut = kind, shortcut
        self.badge, self.live, self.motion, self.phase = 0, False, True, 0
        self.setObjectName('nav')
        self.setCheckable(True)
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.advance)

    def advance(self):
        self.phase = (self.phase + 1) % 24
        self.update()

    def set_signal(self, badge=0, live=False, motion=True):
        self.badge, self.live, self.motion = badge, live, motion
        self.sync()
        self.update()

    def sync(self):
        pulsing = self.live and self.motion and self.isVisible()
        if pulsing != self.timer.isActive():
            self.timer.start() if pulsing else self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor('#e0f1ff' if self.isChecked() or self.underMouse() else '#91a9c1')
        pen = QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = 23.0, self.height() / 2
        if self.kind == 'assistant':
            p.drawEllipse(QPointF(cx, cy), 7, 7)
            p.setBrush(color)
            p.drawEllipse(QPointF(cx, cy), 2.2, 2.2)
        elif self.kind == 'cards':
            p.drawRoundedRect(QRectF(cx - 7, cy - 3, 14, 10), 2.5, 2.5)
            p.drawLine(QPointF(cx - 4.5, cy - 6.5), QPointF(cx + 4.5, cy - 6.5))
        elif self.kind == 'activity':
            p.drawPolyline([QPointF(cx - 8, cy), QPointF(cx - 3.5, cy), QPointF(cx - 1, cy - 6),
                            QPointF(cx + 2, cy + 6), QPointF(cx + 4, cy), QPointF(cx + 8, cy)])
        else:
            for offset, knob in ((-5, 3), (0, -3), (5, 1)):
                p.drawLine(QPointF(cx - 7, cy + offset), QPointF(cx + 7, cy + offset))
                p.setBrush(QColor('#0b1420'))
                p.drawEllipse(QPointF(cx + knob, cy + offset), 2, 2)
                p.setBrush(Qt.BrushStyle.NoBrush)
        right = self.width() - 12
        if self.badge:
            text = str(self.badge) if self.badge < 10 else '9+'
            width = max(18, p.fontMetrics().horizontalAdvance(text) + 10)
            box = QRectF(right - width, cy - 9, width, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#82caff'))
            p.drawRoundedRect(box, 9, 9)
            p.setPen(QColor('#081421'))
            font = p.font()
            font.setBold(True)
            font.setPixelSize(11)
            p.setFont(font)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        elif self.live:
            glow = QColor('#87d2ff')
            wave = abs(12 - self.phase) / 12 if self.motion else 1.0
            glow.setAlpha(int(40 + 60 * wave))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(right - 6, cy), 4 + 3 * (1 - wave), 4 + 3 * (1 - wave))
            p.setBrush(QColor('#87d2ff'))
            p.drawEllipse(QPointF(right - 6, cy), 3.2, 3.2)
        elif self.shortcut:
            p.setPen(QColor('#5f7a92'))
            font = p.font()
            font.setPixelSize(11)
            p.setFont(font)
            p.drawText(QRectF(right - 40, 0, 40, self.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.shortcut)
        p.end()


class ControlDock(QFrame):
    """Dim, never hide, controls; keyboard focus and hover restore contrast."""
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setObjectName('controlDock')
        self.hovered = False
        self.active = False
        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.fade = QPropertyAnimation(self.opacity, b'opacity', self)
        self.fade.setDuration(180)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        QApplication.instance().focusChanged.connect(self.refresh)

    def enterEvent(self, event):
        self.hovered = True
        self.refresh()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.refresh()
        super().leaveEvent(event)

    def refresh(self, *args):
        focus = QApplication.focusWidget()
        focused = focus is not None and self.isAncestorOf(focus)
        target = 1.0 if not self.active or self.hovered or focused else 0.68
        self.fade.stop()
        if self.controller.reduced_motion or not self.isVisible():
            self.opacity.setOpacity(target)
        elif abs(self.opacity.opacity() - target) > 0.01:
            self.fade.setStartValue(self.opacity.opacity())
            self.fade.setEndValue(target)
            self.fade.start()

    def hideEvent(self, event):
        self.fade.stop()
        super().hideEvent(event)


class OrbTransfer(QWidget):
    """Short input-transparent image transfer; source/target keep one session."""
    def __init__(self, pixmap, start, end, finish):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput |
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.pixmap = pixmap
        self.finish = finish
        self.setGeometry(start)
        self.animation = QPropertyAnimation(self, b'geometry', self)
        self.animation.setDuration(280)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setStartValue(start)
        self.animation.setEndValue(end)
        self.animation.finished.connect(self.complete)

    def begin(self):
        self.show()
        self.animation.start()

    def complete(self):
        self.animation.stop()
        self.hide()
        if self.finish:
            callback, self.finish = self.finish, None
            callback()
        self.deleteLater()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(self.rect(), self.pixmap)
        p.end()
