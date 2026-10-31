"""Opt-in macOS echo cancellation: one AVAudioEngine with Voice Processing I/O.

`JARVIS_ECHO_CANCEL=1` turns it on. The speaker and the microphone go through
the same engine, so Apple's canceller hears exactly what Jarvis plays and
removes it from the microphone. That lets Kevin interrupt Jarvis by voice.

`VoiceProcessingDevices` mimics the two sounddevice constructors LocalAudio
uses (RawInputStream / RawOutputStream, PCM16 mono callbacks), so the rest of
the audio path is unchanged. Any failure is raised to LocalAudio, which then
falls back to PortAudio and its half-duplex guard.
"""
from __future__ import annotations

import os
from array import array
from collections import namedtuple
from threading import Lock, Semaphore, Thread
from time import monotonic

PRIMED_BLOCKS = 4  # 80 ms queued ahead of the player: margin for the GIL.
TAP_FRAMES = 2400  # A hint; Core Audio usually delivers about 100 ms.

Timing = namedtuple("Timing", "currentTime outputBufferDacTime")


def echo_cancel_requested(environ=None):
    value = (os.environ if environ is None else environ).get("JARVIS_ECHO_CANCEL", "")
    return value.strip().lower() in {"1", "true", "yes", "oui", "on"}


def pcm16_to_float(data):
    samples = array("h")
    samples.frombytes(bytes(data))
    return array("f", [value / 32768 for value in samples])


def float_to_pcm16(samples):
    return array("h", [max(-32768, min(32767, int(value * 32767))) for value in samples]).tobytes()


class Rechunker:
    """Cut a byte stream into fixed blocks, keeping the remainder for later."""

    def __init__(self, size):
        self.size = size
        self.pending = bytearray()

    def feed(self, data):
        self.pending.extend(data)
        blocks = []
        while len(self.pending) >= self.size:
            blocks.append(bytes(self.pending[:self.size]))
            del self.pending[:self.size]
        return blocks


class VoiceProcessingDevices:
    """One engine shared by both streams; build it once per LocalAudio.open."""

    def __init__(self, avf=None):
        if avf is None:
            import AVFoundation as avf
        self.avf = avf
        self.lock = Lock()
        self.engine = avf.AVAudioEngine.alloc().init()
        # The mixer must exist before voice processing is enabled, otherwise
        # the output unit fails to initialise (-10875) on macOS 14 to 26.
        mixer = self.engine.mainMixerNode()
        microphone = self.engine.inputNode()
        ok, error = microphone.setVoiceProcessingEnabled_error_(True, None)
        if not ok or not microphone.isVoiceProcessingEnabled():
            raise RuntimeError(f"Voice processing unavailable: {error}")
        try:
            # Voice processing ducks every other app by default; keep music
            # in Spotify or a video audible while a session is open.
            microphone.setVoiceProcessingOtherAudioDuckingConfiguration_(
                (False, avf.AVAudioVoiceProcessingOtherAudioDuckingLevelMin))
        except Exception:
            pass  # macOS 13: default ducking, still usable.
        self.player = avf.AVAudioPlayerNode.alloc().init()
        self.engine.attachNode_(self.player)
        self.format = None
        self.mixer = mixer

    def _start_engine(self, samplerate):
        with self.lock:
            if self.format is None:
                self.format = self.avf.AVAudioFormat.alloc().initWithCommonFormat_sampleRate_channels_interleaved_(
                    self.avf.AVAudioPCMFormatFloat32, float(samplerate), 1, False)
                self.engine.connect_to_format_(self.player, self.mixer, self.format)
                self.engine.prepare()
            if not self.engine.isRunning():
                ok, error = self.engine.startAndReturnError_(None)
                if not ok:
                    raise RuntimeError(f"Voice processing engine failed to start: {error}")

    @property
    def running(self):
        return bool(self.engine.isRunning())

    def RawOutputStream(self, device=None, samplerate=24000, channels=1, dtype="int16",
                        blocksize=480, callback=None):
        if device is not None or channels != 1 or dtype != "int16":
            raise ValueError("Echo cancellation uses the default devices, mono PCM16.")
        return _OutputStream(self, samplerate, blocksize, callback)

    def RawInputStream(self, device=None, samplerate=24000, channels=1, dtype="int16",
                       blocksize=480, callback=None):
        if device is not None or channels != 1 or dtype != "int16":
            raise ValueError("Echo cancellation uses the default devices, mono PCM16.")
        return _InputStream(self, samplerate, blocksize, callback)

    def shutdown(self):
        try:
            self.engine.inputNode().removeTapOnBus_(0)
        except Exception:
            pass
        self.player.stop()
        self.engine.stop()


class _OutputStream:
    """Pull model on top of AVAudioPlayerNode: each consumed buffer asks the
    LocalAudio callback for the next 20 ms, like a PortAudio callback.

    A pump thread schedules the buffers. Scheduling from the completion
    handler itself deadlocks against player.stop()."""

    def __init__(self, devices, samplerate, blocksize, callback):
        self.devices, self.samplerate = devices, samplerate
        self.blocksize, self.callback = blocksize, callback
        self.active = False
        self.free = None
        self.pump = None

    def start(self):
        self.devices._start_engine(self.samplerate)
        self.free = Semaphore(PRIMED_BLOCKS)
        self.active = True
        self.devices.player.play()
        self.pump = Thread(target=self._run, name="Jarvis voice processing", daemon=True)
        self.pump.start()

    def _consumed(self):
        self.free.release()

    def _run(self):
        while self.active:
            if not self.free.acquire(timeout=0.1):
                continue
            if not self.active:
                return
            if not self.devices.running:  # Device change: health check reconnects.
                self.active = False
                return
            self._schedule()

    def _schedule(self):
        data = bytearray(self.blocksize * 2)
        now = monotonic()
        self.callback(data, self.blocksize, Timing(now, now + PRIMED_BLOCKS * self.blocksize / self.samplerate), None)
        buffer = self.devices.avf.AVAudioPCMBuffer.alloc().initWithPCMFormat_frameCapacity_(
            self.devices.format, self.blocksize)
        buffer.setFrameLength_(self.blocksize)
        buffer.floatChannelData()[0].as_buffer(self.blocksize)[:] = pcm16_to_float(data).tobytes()
        self.devices.player.scheduleBuffer_completionHandler_(buffer, self._consumed)

    def stop(self):
        self.active = False
        if self.pump is not None:
            self.pump.join(1.0)
            self.pump = None
        self.devices.player.stop()

    abort = stop

    def close(self):
        self.stop()
        self.devices.shutdown()


class _InputStream:
    """Tap on the processed microphone: channel 0, resampled to 24 kHz PCM16
    and cut into the 20 ms blocks LocalAudio and the wake word expect."""

    def __init__(self, devices, samplerate, blocksize, callback):
        self.devices, self.samplerate = devices, samplerate
        self.blocksize, self.callback = blocksize, callback
        self.chunks = Rechunker(blocksize * 2)
        self.resampler = None
        self.rate = None
        self.tapped = False
        self.started = False

    @property
    def active(self):
        return self.started and self.devices.running

    def start(self):
        self.devices._start_engine(self.samplerate)
        if not self.tapped:
            self.devices.engine.inputNode().installTapOnBus_bufferSize_format_block_(
                0, TAP_FRAMES, None, self._tap)
            self.tapped = True
        self.started = True

    def _tap(self, buffer, when):
        if not self.started:
            return
        frames = buffer.frameLength()
        pcm = float_to_pcm16(array("f", bytes(buffer.floatChannelData()[0].as_buffer(frames))))
        rate = int(buffer.format().sampleRate())
        if rate != self.samplerate:
            if self.rate != rate:
                from livekit import rtc
                self.resampler, self.rate = rtc.AudioResampler(rate, self.samplerate, num_channels=1), rate
            pcm = b"".join(bytes(frame.data) for frame in self.resampler.push(bytearray(pcm)))
        for block in self.chunks.feed(pcm):
            self.callback(block, self.blocksize, None, None)

    def stop(self):
        self.started = False
        if self.tapped:
            try:
                self.devices.engine.inputNode().removeTapOnBus_(0)
            except Exception:
                pass
            self.tapped = False
        self.chunks.pending.clear()

    abort = stop

    def close(self):
        self.stop()
