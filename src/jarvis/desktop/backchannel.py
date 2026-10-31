"""Silent visual backchannel: the avatar shows it is listening while you talk.

Pure logic, no Qt and no audio: it only reads the presented state and the
scalar microphone level the UI already receives. Audio is half-duplex, so an
audible "mm-hm" is impossible; a lean, a level-following pulse and a small nod
at short pauses say the same thing without a sound.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class BackchannelFrame:
    """attention: eased 0..1 lean toward the speaker; pulse: 0..1 smoothed
    voice level; nod: 0..1 head-dip envelope (0 at rest)."""
    attention: float = 0.0
    pulse: float = 0.0
    nod: float = 0.0


NEUTRAL = BackchannelFrame()


class LevelSmoother:
    """Envelope follower: quick attack, slow release, so syllables read as one
    breathing pulse rather than flicker."""

    def __init__(self, attack=.035, release=.22):
        self.attack, self.release = attack, release
        self.value = 0.0

    def update(self, level, dt):
        level = max(0.0, min(1.0, level))
        tau = self.attack if level > self.value else self.release
        self.value += (level - self.value) * (1 - math.exp(-dt / tau))
        return self.value

    def reset(self):
        self.value = 0.0


class Backchannel:
    """Small state machine fed every frame with (state, mic level, dt).

    Speech is inferred from the level with an adaptive noise floor and
    hysteresis. A nod fires once the user has spoken for a while and then
    pauses briefly, well before the 1.1 s end-of-turn silence of the VAD.
    """

    MIN_LEVEL = .012        # absolute speech threshold (RMS, 0..1)
    FLOOR_RATIO = 3.0       # speech must stand this far above the noise floor
    RELEASE_RATIO = .6      # hysteresis: stop below this fraction of the on-threshold
    MIN_SPEECH = .5         # seconds of speech before a pause earns a nod
    PAUSE_DELAY = .25       # silence before the nod starts
    NOD_DURATION = .55
    COOLDOWN = 1.6          # between two nod starts

    def __init__(self):
        self.smoother = LevelSmoother()                      # drives the visible pulse
        self.detector = LevelSmoother(attack=.02, release=.08)  # decides speech vs pause
        self.reset()

    def reset(self):
        self.smoother.reset()
        self.detector.reset()
        self.floor = .004
        self.speaking = False
        self.speech_time = self.silence_time = 0.0
        self.since_nod = self.COOLDOWN
        self.nod_time = None
        self.heard = False      # the user spoke in the current turn
        self.attention = 0.0

    def threshold(self):
        return max(self.MIN_LEVEL, self.floor * self.FLOOR_RATIO)

    def _track_floor(self, level, dt):
        # Falls quickly into the gaps between words, rises slowly: speech barely
        # lifts it, a steady fan or hum is absorbed within a few seconds.
        tau = .4 if level < self.floor else 6.0
        self.floor += (level - self.floor) * (1 - math.exp(-dt / tau))
        self.floor = max(.001, min(.05, self.floor))

    def update(self, state, level, dt, enabled=True):
        if not enabled:
            self.reset()
            return NEUTRAL
        dt = max(0.0, min(.25, dt))
        listening = state == 'listening'
        heard_level = level if listening else 0.0
        smooth = self.smoother.update(heard_level, dt)
        voice = self.detector.update(heard_level, dt)
        self.since_nod += dt
        if listening:
            on = self.threshold()
            self.speaking = voice >= (on * self.RELEASE_RATIO if self.speaking else on)
            self._track_floor(level, dt)
            if self.speaking:
                self.heard = True
                self.speech_time += dt
                self.silence_time = 0.0
            else:
                self.silence_time += dt
                if (self.speech_time >= self.MIN_SPEECH and self.silence_time >= self.PAUSE_DELAY
                        and self.since_nod >= self.COOLDOWN and self.nod_time is None):
                    self.nod_time = 0.0
                    self.since_nod = 0.0
                    self.speech_time = 0.0
                # A long silence is a finished turn, not a pause: start afresh.
                if self.silence_time > 1.2:
                    self.speech_time = 0.0
                    self.heard = False
        else:
            self.speaking = self.heard = False
            self.speech_time = self.silence_time = 0.0
            self.nod_time = None
        target = 1.0 if listening and self.heard else 0.0
        self.attention += (target - self.attention) * (1 - math.exp(-dt / (.18 if target else .45)))
        nod = 0.0
        if self.nod_time is not None:
            self.nod_time += dt
            u = self.nod_time / self.NOD_DURATION
            if u >= 1:
                self.nod_time = None
            else:
                nod = nod_envelope(u)
        pulse = min(1.0, math.sqrt(smooth) * 2.2) if listening else 0.0
        return BackchannelFrame(self.attention, pulse * self.attention, nod)


def nod_envelope(u):
    """One soft dip and return over u in [0, 1]; zero at both ends."""
    if u <= 0 or u >= 1:
        return 0.0
    return math.sin(math.pi * u) ** 2
