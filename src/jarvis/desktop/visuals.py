"""Animated approved 2D artwork. Audio arrives as scalar RMS, never PCM."""
from __future__ import annotations

import math
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget
from jarvis.desktop.avatar_motion import (ABSTRACT_IDS, interaction_weights,
    ease_interaction, blended_motion, sample_motion, paint_details)


def tint(color, alpha):
    value = QColor(color)
    value.setAlpha(max(0, min(255, int(alpha))))
    return value


# Per-state accent colour and idle "awakeness". Both are eased toward (never
# snapped to) so a change of state reads as a living transition, not a jump; the
# glow drives a gentle breathing even in silence so the orb is never inert.
STATE_COLORS = {
    'thinking': '#bea5ff', 'error': '#f0a7ba', 'muted': '#6a8399',
    'starting': '#9ad0ea', 'listening': '#87e3ff', 'speaking': '#8af0e0',
    'off': '#87e3ff', 'success': '#8af0be',
}
STATE_GLOW = {
    'off': 0.0, 'muted': 0.12, 'starting': 0.45, 'listening': 0.55,
    'speaking': 0.5, 'thinking': 0.72, 'error': 0.45, 'success': 0.7,
}
_DEFAULT_COLOR = '#87e3ff'
_DEFAULT_GLOW = 0.35


def _ease_color(current, target, t):
    return QColor(
        round(current.red() + (target.red() - current.red()) * t),
        round(current.green() + (target.green() - current.green()) * t),
        round(current.blue() + (target.blue() - current.blue()) * t),
    )


class Orb(QWidget):
    def __init__(self, size=320):
        super().__init__()
        self.setFixedSize(size, size)
        self.phase = 0.0
        self.appearance = 'nova_bot'
        self.previous_frame = self.frame_image = self.frame_key = None
        self.transition = 1.0
        self.state = 'off'
        self.interaction = interaction_weights('off')
        self.motion = True
        self.target = self.energy = 0.0
        # Eased presentation state, distinct from the raw logical state above.
        self.accent = QColor(_DEFAULT_COLOR)
        self.glow = 0.0
        self.setAccessibleName('État vocal de Jarvis')
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)

    def _target_color(self):
        from jarvis.desktop.appearances import BY_ID
        return QColor(STATE_COLORS.get(self.state, BY_ID[self.appearance].accent))

    def _target_glow(self):
        return STATE_GLOW.get(self.state, _DEFAULT_GLOW)

    def showEvent(self, event):
        if self.motion:
            self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def set_motion(self, enabled):
        if self.motion == enabled:
            return
        self.motion = enabled
        if enabled and self.isVisible():
            self.timer.start()
        else:
            self.timer.stop()
            self.energy = 0.0
        self.update()

    def set_levels(self, incoming, outgoing):
        # Perceptual scale, independent of decorative idle breathing.
        level = outgoing if outgoing > 0 else incoming
        self.target = min(1.0, math.sqrt(max(0.0, level)) * 2.2)

    def tick(self):
        self.interaction = ease_interaction(self.interaction, self.state)
        self.transition = min(1.0, self.transition + .12)
        self.phase += (.012 + .014*self.interaction['thinking']) if self.appearance in ABSTRACT_IDS else (.026 if self.state == 'thinking' else .012)
        speed = 0.45 if self.target > self.energy else 0.16
        self.energy += (self.target - self.energy) * speed
        # Ease the presentation toward the current state so transitions glide.
        self.glow += (self._target_glow() - self.glow) * 0.08
        self.accent = _ease_color(self.accent, self._target_color(), 0.09)
        self.update()

    def set_appearance(self, appearance):
        from jarvis.desktop.appearances import valid_appearance
        appearance = valid_appearance(appearance)
        if appearance != self.appearance:
            self.previous_frame = self.current_image()
            self.appearance = appearance
            self.transition = 0.0
            self.update()

    def current_image(self):
        from jarvis.desktop.avatar_assets import pose_image
        return pose_image(self.appearance, self.state)

    def paintEvent(self, event):
        image = self.current_image()
        key = (self.appearance, self.state)
        if key != self.frame_key:
            if self.frame_image is not None:
                self.previous_frame = self.frame_image
                self.transition = 0.0
            self.frame_key, self.frame_image = key, image
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        side = min(self.width(), self.height())
        p.translate(self.width()/2, self.height()/2)
        energy = self.energy if self.motion else 0.0
        phase = self.phase if self.motion else 0.0
        accent = self.accent if self.motion else self._target_color()
        halo = QRadialGradient(QPointF(), side*.5)
        breath = (1 + math.sin(phase*2)) * .5 if self.motion else 0
        activation = self.glow if self.motion else self._target_glow()
        halo.setColorAt(0, tint(accent, 32 + 20*activation + 10*breath + 35*energy))
        halo.setColorAt(1, tint(accent, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QPointF(), side*.49, side*.49)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(tint(accent, 65), .8))
        p.drawEllipse(QRectF(-side*.44, side*.43, side*.88, side*.08))
        p.save()
        frame = (blended_motion(self.appearance, phase, energy, self.interaction, self.motion)
                 if self.appearance in ABSTRACT_IDS else
                 sample_motion(self.appearance, phase, energy, self.state, self.motion))
        p.translate(frame.x * side, frame.y * side)
        p.rotate(frame.rotation)
        p.scale(frame.sx, frame.sy)
        def draw(frame, opacity):
            size = frame.size().scaled(int(side*.86), int(side*.86), Qt.AspectRatioMode.KeepAspectRatio)
            rect = QRectF(-size.width()/2, -size.height()/2, size.width(), size.height())
            p.setOpacity(opacity)
            p.drawImage(rect, frame)
        blend = self.transition if self.motion else 1.0
        if self.previous_frame is not None and blend < 1:
            draw(self.previous_frame, 1-blend)
        draw(image, blend)
        p.restore()
        # Reduced motion has no moving decorative layers, including on repaint.
        if self.motion:
            paint_details(p, self.appearance, phase, energy, self.state, side, self.interaction)
        p.end()
