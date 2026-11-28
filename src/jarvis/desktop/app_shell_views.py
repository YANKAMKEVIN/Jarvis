"""Window placement and switching between the full, compact and orb views."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QGraphicsOpacityEffect

from jarvis.desktop.surfaces import OrbTransfer


class ShellViewsMixin:
    """Window placement and switching between the full, compact and orb views. Mixed into DesktopShell."""

    def hide_windows(self):
        # Never strand a running assistant without a way to reopen it.
        if not self.has_tray:
            return
        self.finish_transfer()
        self.remember_companion()
        self.remember_orb()
        for window in (self.full, self.compact, self.orb_window):
            window.hide()

    def restore_companion(self):
        if self.position_restored:
            return
        self.position_restored = True
        self.restore_position(self.compact, 'companion/position')

    def restore_position(self, window, key):
        point = self.settings.value(key)
        screens = QGuiApplication.screens()
        screen = next((s for s in screens if isinstance(point, QPoint) and
                       s.availableGeometry().contains(point)), QGuiApplication.primaryScreen())
        if screen is None:
            return
        area = screen.availableGeometry()
        if not isinstance(point, QPoint):
            point = QPoint(area.right() - window.width() - 24,
                           area.bottom() - window.height() - 24)
        x = max(area.left(), min(point.x(), area.right() - window.width() + 1))
        y = max(area.top(), min(point.y(), area.bottom() - window.height() + 1))
        window.move(x, y)

    def remember_companion(self):
        if self.position_restored and not self.controller.demo:
            origin = getattr(self.compact, "dance_origin", None)
            self.settings.setValue("companion/position", origin if origin is not None else self.compact.pos())

    def remember_orb(self):
        if self.orb_position_restored and not self.controller.demo:
            self.settings.setValue('orb/position', self.orb_window.pos())

    def visible_window(self):
        return next((w for w in (self.full, self.compact, self.orb_window) if w.isVisible()), self.full)

    def show_orb(self):
        if not self.orb_position_restored:
            self.orb_position_restored = True
            self.restore_position(self.orb_window, 'orb/position')
        self.present(self.orb_window, self.visible_window())

    def show_details(self):
        self.show_full()
        self.finish_transfer()
        self.full.navigate(1 if self.controller.cards else 2)

    def show_mission_details(self):
        self.show_full()
        self.finish_transfer()
        self.full.navigate(2)

    def finish_transfer(self):
        if self.transfer is not None:
            self.transfer.complete()

    def motion_changed(self):
        if self.controller.reduced_motion:
            self.finish_transfer()

    def present(self, target, source):
        self.finish_transfer()
        animate = source.assistant.orb.isVisible() and not target.isVisible() and not self.controller.reduced_motion
        pixmap = source.assistant.orb.grab() if animate else None
        start = QRect(source.assistant.orb.mapToGlobal(QPoint()), source.assistant.orb.size())
        if source is self.compact:
            self.remember_companion()
        if source is self.orb_window:
            self.remember_orb()
        target.show()
        for window in (self.full, self.compact, self.orb_window):
            if window is not target:
                window.hide()
        target.raise_()
        target.activateWindow()
        # Keep command controls discoverable, with no forced focus on an action.
        if animate:
            orb = target.assistant.orb
            end = QRect(orb.mapToGlobal(QPoint()), orb.size())
            effect = QGraphicsOpacityEffect(orb)
            effect.setOpacity(0.0)
            orb.setGraphicsEffect(effect)
            def finished():
                orb.setGraphicsEffect(None)
                self.transfer = None
            self.transfer = OrbTransfer(pixmap, start, end, finished)
            self.transfer.begin()

    def show_full(self):
        if self.compact.isVisible() or self.orb_window.isVisible():
            self.full.navigate(0)
        self.present(self.full, self.visible_window())

    def show_compact(self):
        self.restore_companion()
        self.present(self.compact, self.visible_window())

    def switch_view(self):
        self.show_full() if self.compact.isVisible() else self.show_compact()
