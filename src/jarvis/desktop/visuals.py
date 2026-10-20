"""Locally painted holographic orb. Audio arrives as scalar RMS, never PCM."""
from __future__ import annotations

import math
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QLinearGradient
from PySide6.QtWidgets import QWidget


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
    'off': '#87e3ff',
}
STATE_GLOW = {
    'off': 0.0, 'muted': 0.12, 'starting': 0.45, 'listening': 0.55,
    'speaking': 0.5, 'thinking': 0.72, 'error': 0.45,
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
        self.state = 'off'
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
        return QColor(STATE_COLORS.get(self.state, _DEFAULT_COLOR))

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
        self.phase += 0.026 if self.state == 'thinking' else 0.012
        speed = 0.45 if self.target > self.energy else 0.16
        self.energy += (self.target - self.energy) * speed
        # Ease the presentation toward the current state so transitions glide.
        self.glow += (self._target_glow() - self.glow) * 0.08
        self.accent = _ease_color(self.accent, self._target_color(), 0.09)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = self.width()
        p.translate(side / 2, side / 2)
        # Reduced motion: hold a correct still frame (target colour/glow, no
        # audio energy, no breathing) instead of a frozen mid-transition.
        energy = self.energy if self.motion else 0.0
        phase = self.phase
        accent = self.accent if self.motion else self._target_color()
        activation = self.glow if self.motion else self._target_glow()
        breath = (0.5 + 0.5 * math.sin(phase * 2)) if self.motion else 0.0
        # Idle breathing of the sphere, scaled by how awake the state is, plus
        # the real audio envelope on top.
        radius = side * (0.302 + 0.018 * energy + 0.024 * breath * activation)
        halo = QRadialGradient(QPointF(), side * 0.49)
        halo.setColorAt(0, tint(accent, int(58 + energy * 45)))
        halo.setColorAt(0.55, tint(accent, int(23 + breath * 8)))
        halo.setColorAt(1, tint(accent, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QPointF(), side * 0.49, side * 0.49)

        # Fine lens rings and quiet orbital landmarks, not a progress meter.
        p.setBrush(Qt.BrushStyle.NoBrush)
        for scale, alpha in ((1.18, 33), (1.24, 17), (1.39, 12)):
            p.setPen(QPen(tint(accent, alpha), 0.7))
            p.drawEllipse(QPointF(), radius * scale, radius * scale)
        for angle in (28, 145, 258):
            p.save()
            # Organic drift: a slow sine wobble over the steady rotation.
            p.rotate(angle + phase * 8 + 6 * math.sin(phase * 0.6 + angle))
            ring = QRectF(-radius * 1.18, -radius * 1.18, radius * 2.36, radius * 2.36)
            p.setPen(QPen(tint(accent, 125), 1.2))
            p.drawArc(ring, 0, 17 * 16)
            p.restore()

        glass = QRadialGradient(QPointF(-radius * 0.32, -radius * 0.45), radius * 1.65)
        glass.setColorAt(0, QColor('#2e5267'))
        glass.setColorAt(0.36, QColor('#102e40'))
        glass.setColorAt(0.77, QColor('#081423'))
        glass.setColorAt(1, QColor('#1c3c50'))
        p.setBrush(glass)
        p.setPen(QPen(tint(accent, 100), 0.8))
        p.drawEllipse(QPointF(), radius, radius)
        clip = QPainterPath()
        clip.addEllipse(QPointF(), radius - 1, radius - 1)
        p.save()
        p.setClipPath(clip)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Latitude filaments form a breathing volume, with a real audio envelope.
        for band in range(19):
            latitude = (band - 9) / 10
            width = radius * math.sqrt(1 - latitude * latitude)
            path = QPainterPath()
            for step in range(65):
                u = step / 64
                x = (u * 2 - 1) * width
                depth = math.sin(u * math.pi)
                wave = math.sin(u * math.pi * 3 + phase * 2 + band * 0.32)
                y = latitude * radius * 0.9 + depth * wave * radius * (0.12 + 0.05 * breath * activation + energy * 0.18)
                point = QPointF(x, y)
                path.moveTo(point) if step == 0 else path.lineTo(point)
            gradient = QLinearGradient(-width, 0, width, 0)
            gradient.setColorAt(0, tint(accent, 10))
            gradient.setColorAt(0.45, tint(accent, 95 + int(energy * 95)))
            gradient.setColorAt(0.7, tint('#e7fbff', 155))
            gradient.setColorAt(1, tint(accent, 15))
            p.setPen(QPen(gradient, 0.8 + energy * 0.6))
            p.drawPath(path)

        core = QRadialGradient(QPointF(radius * 0.12, radius * 0.02), radius * 0.69)
        core.setColorAt(0, tint('#e5faff', 115 + 90 * energy + 40 * breath * activation))
        core.setColorAt(0.12, tint(accent, 85 + 90 * energy + 30 * breath * activation))
        core.setColorAt(0.48, tint(accent, 22))
        core.setColorAt(1, tint(accent, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(core)
        p.drawEllipse(QPointF(radius * 0.12, radius * 0.02), radius * 0.69, radius * 0.69)
        # Sparse points are fixed in count, with deterministic motion.
        for index in range(24):
            angle = index * 2.39996 + phase * 0.16 + 0.4 * math.sin(phase * 0.3 + index)
            distance = radius * math.sqrt((index + 1) / 27)
            x, y = math.cos(angle) * distance, math.sin(angle) * distance
            p.setBrush(tint('#d7f5ff', 70 + index % 4 * 28))
            p.drawEllipse(QPointF(x, y), 0.7, 0.7)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(tint('#e1f7ff', 110), 0.8))
        p.drawArc(QRectF(-radius, -radius, radius * 2, radius * 2), 30 * 16, 100 * 16)
        p.end()
