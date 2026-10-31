"""Measure how much of Jarvis's own voice the microphone still hears.

Plays five seconds of synthetic speech (macOS `say`) through LocalAudio, once
with the half-duplex PortAudio path and once with voice processing, and
reports the normalised correlation between what was played and what the
microphone captured. Near 0: the echo is gone; 0.3 and above: clearly heard.
The guard is disabled during the measurement; nothing leaves the Mac.

Run it in a quiet room, speaker volume as you use Jarvis (30 % or more):
    PYTHONPATH=src .venv/bin/python scripts/check_echo_cancel.py
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from livekit import rtc

from jarvis.desktop.live_audio import LocalAudio, SAMPLE_RATE

PHRASE = ("Bonjour Kevin, ceci est un essai d'annulation d'écho. Je parle quelques secondes "
          "pour mesurer ce que le micro entend encore de ma propre voix.")


def speech_pcm(folder):
    aiff, wav = Path(folder, "speech.aiff"), Path(folder, "speech.wav")
    subprocess.run(["say", "-o", str(aiff), PHRASE], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEI16@{SAMPLE_RATE}", "-c", "1", str(aiff), str(wav)], check=True)
    with wave.open(str(wav)) as source:
        pcm = np.frombuffer(source.readframes(SAMPLE_RATE * 5), dtype=np.int16).astype(float)
    return (pcm * (29000 / max(1.0, np.abs(pcm).max()))).astype(np.int16).tobytes()  # Loudest clean level.


def correlation(captured, reference):
    seg = np.frombuffer(captured, dtype=np.int16).astype(float)
    ref = np.frombuffer(reference, dtype=np.int16).astype(float)
    best = 0.0
    for lag in range(0, max(1, len(seg) - len(ref)), 24):  # 1 ms steps, up to ~0.7 s delay.
        window = seg[lag:lag + len(ref)]
        if len(window) < len(ref):
            break
        best = max(best, abs(window @ ref) / (np.linalg.norm(window) * np.linalg.norm(ref) + 1e-9))
    return best


async def measure(pcm, echo_cancel):
    audio = LocalAudio(asyncio.get_running_loop(), echo_cancel=echo_cancel)
    audio.allow_barge_in = True  # Capture everything: this is what we measure.
    audio.open()
    captured = []
    async def drain():
        while True:
            frame = await audio.input.__anext__()
            captured.append((time.monotonic(), bytes(frame.data)))
    task = asyncio.create_task(drain())
    try:
        await asyncio.sleep(2.0)  # Let voice processing settle.
        start = time.monotonic()
        for index in range(0, len(pcm), 960):
            chunk = pcm[index:index + 960]
            await audio.output.capture_frame(rtc.AudioFrame(data=chunk, sample_rate=SAMPLE_RATE,
                num_channels=1, samples_per_channel=len(chunk) // 2))
        audio.output.flush()
        await asyncio.sleep(start + 6.0 - time.monotonic())
    finally:
        task.cancel()
        mode, error = audio.echo_cancelled, audio.echo_cancel_error
        audio.close()
    heard = b"".join(data for at, data in captured if start - 0.1 < at < start + 5.8)
    return mode, error, correlation(heard, pcm)


async def main():
    with tempfile.TemporaryDirectory() as folder:
        pcm = speech_pcm(folder)
    for echo_cancel in (False, True):
        mode, error, value = await measure(pcm, echo_cancel)
        label = "annulation d'écho" if mode else "PortAudio (sans annulation)"
        print(f"{label:30} corrélation = {value:.3f}" + (f"  · repli : {error}" if error else ""), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
    sys.stdout.flush()
    os._exit(0)  # livekit's FFI handles assert at interpreter shutdown.
