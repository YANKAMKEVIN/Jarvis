"""Bounded, temporary 2D dance choreography; never changes saved position."""
import math
import time
from PySide6.QtCore import QObject, QTimer
from jarvis.desktop.avatar_motion import MotionFrame

DURATION = 8.0
# Bust-only Holo Face remains a head bob; abstract appearances have no steps.
DANCERS = frozenset({'nova_bot', 'neo_guide', 'kitsune', 'digital_avatar', 'synth_companion', 'holo_face'})


def dance_frame(appearance, elapsed):
    if appearance not in DANCERS or not 0 < elapsed < DURATION:
        return MotionFrame(0, 0, 0, 1, 1)
    envelope = min(1., elapsed / .5, (DURATION - elapsed) / .5)
    beat = elapsed * math.tau * 2
    variant = sorted(DANCERS).index(appearance)
    sway = math.sin(beat / 2)
    hop = abs(math.sin(beat))
    amplitude = .5 if appearance == 'holo_face' else 1.
    return MotionFrame(envelope * .035 * sway * amplitude,
                       -envelope * .025 * hop * amplitude,
                       envelope * (5 + variant * .7) * sway,
                       1 + envelope * .025 * math.sin(beat),
                       1 - envelope * .025 * math.sin(beat))


def travel(elapsed):
    envelope = max(0., min(1., elapsed / .5, (DURATION - elapsed) / .5))
    return (round(32 * envelope * math.sin(elapsed * math.tau / 4)),
            round(-7 * envelope * abs(math.sin(elapsed * math.tau))))


class AvatarDance(QObject):
    def __init__(self, controller, clock=time.monotonic):
        super().__init__(controller)
        self.controller, self.clock, self.started = controller, clock, None
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)

    @property
    def elapsed(self):
        return 0. if self.started is None else self.clock() - self.started

    @property
    def active(self):
        return self.started is not None

    def start(self):
        c = self.controller
        if c.reduced_motion or c.appearance not in DANCERS:
            return False
        if not self.active:
            self.started = self.clock()
            self.timer.start()
            c.changed.emit()
        return True

    def stop(self):
        if self.active:
            self.started = None
            self.timer.stop()
            self.controller.changed.emit()

    def tick(self):
        c = self.controller
        if self.elapsed >= DURATION or c.reduced_motion or c.appearance not in DANCERS or c.voice_state == 'error':
            self.stop()
        else:
            c.changed.emit()
