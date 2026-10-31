"""A short, upbeat loop synthesized on the fly for the avatar dance: kick, bass
and a plucked arpeggio at 120 bpm, mono PCM16 at the voice output rate. Kept
quiet (well under Jarvis's voice) and faded in and out like the dance itself.
No audio file ships with Jarvis, and nothing is downloaded.
"""
from array import array
from functools import lru_cache
from math import exp, pi, sin
import random

BPM = 120
PEAK = 5200  # Speech peaks far higher; the loop stays a background.
FADE_SECONDS = 0.4

# One chord root per bar (A minor, F, C, G), as bass and arpeggio frequencies.
_BARS = (
    (110.00, (440.00, 523.25, 659.25, 523.25)),
    (87.31, (349.23, 440.00, 523.25, 440.00)),
    (130.81, (392.00, 523.25, 659.25, 523.25)),
    (98.00, (392.00, 493.88, 587.33, 493.88)),
)


@lru_cache(maxsize=4)
def dance_track(seconds, rate):
    """The loop as raw little-endian PCM16 bytes, `seconds` long."""
    total = int(seconds * rate)
    beat = int(rate * 60 / BPM)
    eighth = beat // 2
    noise = random.Random(7)  # Same hi-hat every time.
    fade = int(FADE_SECONDS * rate)
    samples = array("h")
    for n in range(total):
        bar = (n // (beat * 4)) % len(_BARS)
        root, arpeggio = _BARS[bar]
        in_beat = n % beat
        in_eighth = n % eighth
        t_beat = in_beat / rate
        t_eighth = in_eighth / rate
        # Kick: a falling sine thump on every beat.
        kick = sin(2 * pi * (55 + 90 * exp(-t_beat * 30)) * t_beat) * exp(-t_beat * 9)
        # Bass on the beat, a short plucked note.
        bass = sin(2 * pi * root * t_beat) * exp(-t_beat * 5)
        # Arpeggio on eighths, cycling through the bar's chord.
        note = arpeggio[(n // eighth) % len(arpeggio)]
        pluck = (sin(2 * pi * note * t_eighth)
                 + 0.3 * sin(4 * pi * note * t_eighth)) * exp(-t_eighth * 14)
        # Hi-hat: a tiny noise burst on the off-beat.
        hat = (noise.uniform(-1, 1) * exp(-(in_beat - eighth) / rate * 60)
               if in_beat >= eighth else 0.0)
        value = 0.45 * kick + 0.3 * bass + 0.22 * pluck + 0.08 * hat
        envelope = min(1.0, n / fade, (total - n) / fade) if fade else 1.0
        samples.append(int(max(-1.0, min(1.0, value)) * PEAK * envelope))
    return samples.tobytes()
