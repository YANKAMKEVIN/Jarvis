"""Animated approved 2D artwork. Audio arrives as scalar RMS, never PCM."""
from __future__ import annotations

import math
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QCursor, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget
from jarvis.desktop.avatar_motion import (ABSTRACT_IDS, interaction_weights,
    ease_interaction, blended_motion, sample_motion, paint_details)
from jarvis.desktop.backchannel import NEUTRAL, Backchannel


def tint(color, alpha):
    value = QColor(color)
    value.setAlpha(max(0, min(255, int(alpha))))
    return value


# Per-state accent colour and idle "awakeness". Both are eased toward (never
# snapped to) so a change of state reads as a living transition, not a jump; the
# glow drives a gentle breathing even in silence so the orb is never inert.
STATE_COLORS = {
    'waiting': '#f6cf88', 'thinking': '#bea5ff', 'error': '#f0a7ba', 'muted': '#6a8399',
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
        self.pedestal = True
        self.dance = None
        self.tracking = True
        self.articulated = False
        self.gaze = (0.,0.)
        self.wave_ticks = 0
        self.phase = 0.0
        self.appearance = 'nova_bot'
        self.previous_frame = self.frame_image = self.frame_key = None
        self.transition = 1.0
        self.state = 'off'
        self.interaction = interaction_weights('off')
        self.motion = True
        self.target = self.energy = 0.0
        # Silent "I'm listening" cues while the user talks (see backchannel.py).
        self.backchannel = Backchannel()
        self.backchannel_enabled = True
        self.mic_level = 0.0
        self.listen = NEUTRAL
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
            self.backchannel.reset()
            self.listen = NEUTRAL
        self.update()

    def set_levels(self, incoming, outgoing):
        # Perceptual scale, independent of decorative idle breathing.
        level = outgoing if outgoing > 0 else incoming
        self.target = min(1.0, math.sqrt(max(0.0, level)) * 2.2)
        self.mic_level = max(0.0, incoming)

    def greet(self):
        if self.motion:self.wave_ticks=45;self.update()

    def tick(self):
        self.wave_ticks=max(0,self.wave_ticks-1)
        if self.tracking:
            cursor=self.mapFromGlobal(QCursor.pos());scale=max(1,self.width()/2)
            target=(max(-1.,min(1.,(cursor.x()-self.width()/2)/scale)),max(-1.,min(1.,(cursor.y()-self.height()/2)/scale)))
        else:target=(0.,0.)
        self.gaze=tuple(value+(wanted-value)*.12 for value,wanted in zip(self.gaze,target))
        self.interaction = ease_interaction(self.interaction, self.state)
        self.transition = min(1.0, self.transition + .12)
        self.phase += (.012 + .014*self.interaction['thinking']) if self.appearance in ABSTRACT_IDS else (.026 if self.state == 'thinking' else .012)
        speed = 0.45 if self.target > self.energy else 0.16
        self.energy += (self.target - self.energy) * speed
        # Ease the presentation toward the current state so transitions glide.
        self.glow += (self._target_glow() - self.glow) * 0.08
        self.accent = _ease_color(self.accent, self._target_color(), 0.09)
        dancing = bool(self.dance and self.dance.active)
        self.listen = self.backchannel.update(self.state, self.mic_level, self.timer.interval()/1000,
                                              self.backchannel_enabled and not dancing)
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
        state = 'success' if self.motion and self.wave_ticks else self.state
        if self.motion and self.dance and self.dance.active:
            state = ("listening", "success", "speaking", "success")[int(self.dance.elapsed * 2) % 4]
        return pose_image(self.appearance, state)

    def paintEvent(self, event):
        image = self.current_image()
        key = (self.appearance, image.cacheKey())
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
        listen = self.listen if self.motion and self.backchannel_enabled else NEUTRAL
        if listen.attention > .01:
            # A thin ring that breathes with the user's voice: "I hear you".
            radius = side*(.43 + .025*listen.pulse - .006*listen.nod)
            p.setPen(QPen(tint(accent, (60 + 150*listen.pulse) * listen.attention), 1.5 + 1.5*listen.pulse))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(), radius, radius)
            p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(tint(accent, 65), .8))
        if self.pedestal:
            p.drawEllipse(QRectF(-side*.44, side*.43, side*.88, side*.08))
        p.save()
        frame = (blended_motion(self.appearance, phase, energy, self.interaction, self.motion)
                 if self.appearance in ABSTRACT_IDS else
                 sample_motion(self.appearance, phase, energy, self.state, self.motion))
        if self.motion and self.dance and self.dance.active:
            from jarvis.desktop.avatar_dance import dance_frame
            frame = dance_frame(self.appearance, self.dance.elapsed)
        p.translate(frame.x * side + (self.gaze[0]*side*.007 if self.motion and self.tracking else 0), frame.y * side)
        if listen.attention > .01 or listen.nod:
            # Lean in slightly while listening; nod = a small dip with a forward tilt.
            p.translate(0, side*(.006*listen.attention + .024*listen.nod))
        p.rotate(frame.rotation + 2*listen.nod)
        p.scale(frame.sx * (1 + .006*listen.pulse), frame.sy * (1 + .006*listen.pulse - .015*listen.nod))
        def draw(frame, opacity):
            size = frame.size().scaled(int(side*.86), int(side*.86), Qt.AspectRatioMode.KeepAspectRatio)
            rect = QRectF(-size.width()/2, -size.height()/2, size.width(), size.height())
            p.setOpacity(opacity)
            p.drawImage(rect, frame)
        if self.articulated:
            from jarvis.desktop.articulated_avatar import paint_rig
            dancing=bool(self.motion and self.dance and self.dance.active)
            rig_phase=self.dance.elapsed if dancing else phase
            if paint_rig(p,self.appearance,side,rig_phase,self.state,self.gaze if self.motion else (0,0),dancing,bool(self.motion and self.wave_ticks)):
                p.restore();p.end();return
        blend = self.transition if self.motion else 1.0
        if self.previous_frame is not None and blend < 1:
            draw(self.previous_frame, 1-blend)
        draw(image, blend)
        p.restore()
        # Reduced motion has no moving decorative layers, including on repaint.
        if self.motion:
            paint_details(p, self.appearance, phase, energy, self.state, side, self.interaction)
        p.end()
