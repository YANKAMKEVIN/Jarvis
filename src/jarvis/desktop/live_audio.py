"""Local PCM devices for LiveKit's public AudioInput/AudioOutput interfaces.

Imported only on explicit voice activation. Audio is bounded in RAM, never saved.
PortAudio callbacks never touch Qt or the asyncio session directly.
"""
from __future__ import annotations

import asyncio
from array import array
from math import pi, sin
from collections import deque
from queue import Empty, Full, Queue
from threading import Event, Lock
from time import monotonic

from livekit import rtc
from livekit.agents.voice.io import AudioInput, AudioOutput, AudioOutputCapabilities
from jarvis.desktop.devices import AudioDeviceError, pcm_level, resolve_device

SAMPLE_RATE = 24000
BLOCK_SAMPLES = 480  # 20 ms, mono PCM16
ECHO_TAIL_SECONDS = 0.25
CALLBACK_TIMEOUT_SECONDS = 3.0


class MicrophoneInput(AudioInput):
    def __init__(self, suppressed=lambda: False):
        super().__init__(label="Jarvis microphone")
        self.frames = Queue(maxsize=25)  # At most half a second of speech.
        self.closed = False
        self.tail_frames = 0
        self.suppressed = suppressed

    def push(self, data):
        if self.closed:
            return
        try:
            self.frames.put_nowait(bytes(data))
        except Full:
            try:
                self.frames.get_nowait()
            except Empty:
                pass
            try:
                self.frames.put_nowait(bytes(data))
            except Full:
                pass

    def clear(self):
        self.tail_frames = 0
        while True:
            try:
                self.frames.get_nowait()
            except Empty:
                return

    async def __anext__(self):
        while not self.closed:
            try:
                data = self.frames.get_nowait()
            except Empty:
                if self.tail_frames:
                    await asyncio.sleep(.02)
                    if not self.tail_frames: continue
                    self.tail_frames-=1
                    data=bytes(BLOCK_SAMPLES*2)
                elif self.suppressed():
                    # Keep the server clock/VAD moving while speaker feedback is
                    # blocked. These are synthetic zeros, never microphone PCM.
                    await asyncio.sleep(.02)
                    if self.closed or not self.suppressed():
                        continue
                    data = bytes(BLOCK_SAMPLES * 2)
                else:
                    await asyncio.sleep(0.01)
                    continue
            return rtc.AudioFrame(data=data, sample_rate=SAMPLE_RATE,
                                  num_channels=1, samples_per_channel=len(data) // 2)
        raise StopAsyncIteration


class SpeakerOutput(AudioOutput):
    def __init__(self, loop):
        super().__init__(label="Jarvis speaker", sample_rate=SAMPLE_RATE,
                         capabilities=AudioOutputCapabilities(pause=False))
        self.loop = loop
        self.lock = Lock()
        self.queue = deque()
        self.segments = {}
        self.segment = 0
        self.open_segment = False
        self.buffered_bytes = 0
        self.closed = False

    async def capture_frame(self, frame):
        if frame.sample_rate != SAMPLE_RATE or frame.num_channels != 1:
            raise ValueError("Unsupported desktop audio format")
        # Backpressure prevents an arbitrarily long model answer filling RAM.
        while not self.closed:
            with self.lock:
                buffered = self.buffered_bytes
            if buffered < SAMPLE_RATE * 2:  # One second of PCM16.
                break
            await asyncio.sleep(0.01)
        if self.closed:
            return
        await super().capture_frame(frame)
        with self.lock:
            if not self.open_segment:
                self.segment += 1
                self.segments[self.segment] = 0
                self.open_segment = True
            data = bytes(frame.data)
            self.queue.append((self.segment, data))
            self.buffered_bytes += len(data)

    def flush(self):
        super().flush()
        with self.lock:
            if self.open_segment:
                self.queue.append((self.segment, None))  # Playback boundary.
                self.open_segment = False

    def read(self, size, latency=0):
        """Called by PortAudio. Returns PCM padded with silence, never blocks."""
        output = bytearray()
        ended = []
        with self.lock:
            while self.queue and len(output) < size:
                segment, data = self.queue.popleft()
                if data is None:
                    ended.append(segment)
                    continue
                count = min(len(data), size - len(output))
                output.extend(data[:count])
                self.buffered_bytes -= count
                self.segments[segment] += count
                if count < len(data):
                    self.queue.appendleft((segment, data[count:]))
            # Consume boundaries even when the final sample filled the block.
            while self.queue and self.queue[0][1] is None:
                ended.append(self.queue.popleft()[0])
        for segment in ended:
            self.loop.call_soon_threadsafe(self._schedule_finish, segment, max(0, latency))
        output.extend(bytes(size - len(output)))
        return bytes(output)

    def _schedule_finish(self, segment, latency):
        self.loop.call_later(latency, self._finish, segment, False)

    def _finish(self, segment, interrupted):
        with self.lock:
            played = self.segments.pop(segment, None)
        if played is not None:
            self.on_playback_finished(playback_position=played / (SAMPLE_RATE * 2),
                                      interrupted=interrupted)

    def clear_buffer(self):
        super().flush()
        with self.lock:
            self.queue.clear()
            self.buffered_bytes = 0
            self.open_segment = False
            pending = list(self.segments)
        for segment in pending:
            self._finish(segment, True)


class LocalAudio:
    def __init__(self, loop, devices=None, clock=monotonic):
        if devices is None:
            import sounddevice as devices
        self.devices = devices
        self.input = MicrophoneInput(lambda: self.mic_open and self.input_suppressed)
        self.output = SpeakerOutput(loop)
        self.microphone = None
        self.speaker = None
        self.mic_open = False
        self.quiet = False
        self.allow_barge_in = False
        self.clock = clock
        self.capture_lock = Lock()
        self.suppress_until = 0.0
        self.input_meter = (0.0, 0.0)
        self.output_meter = (0.0, 0.0)
        self.cue_lock = Lock()
        self.cue = b""
        self.cue_guarded = True
        self.input_device = None
        self.output_device = None
        self.default_snapshot=None
        self.last_default_check=0
        self.last_input_callback = None
        self.last_output_callback = None
        # Wake-word gate: while asleep, capture feeds only the local detector.
        self.wake = None
        self.asleep = False
        self.woke = Event()

    def configure_devices(self, input_choice, output_choice):
        self.input_device = resolve_device(self.devices, input_choice, 'input')
        self.output_device = resolve_device(self.devices, output_choice, 'output')

    def read_defaults(self):
        try:
            pair=tuple(self.devices.default.device)
            return pair if len(pair)==2 and all(isinstance(v,int) for v in pair) else None
        except (AttributeError,TypeError):return None

    def check_health(self):
        now=self.clock()
        if now-self.last_default_check>=2:
            self.last_default_check=now
            defaults=self.read_defaults()
            if defaults is not None and self.default_snapshot is not None:
                if ((self.input_device is None and defaults[0]!=self.default_snapshot[0]) or
                    (self.output_device is None and defaults[1]!=self.default_snapshot[1])):
                    raise AudioDeviceError('Le périphérique système a changé. Reconnexion audio nécessaire.')
        try:
            healthy = (self.speaker is not None and self.speaker.active
                       and (not self.mic_open or (self.microphone is not None and self.microphone.active)))
        except Exception:
            healthy = False
        if not healthy:
            raise AudioDeviceError('Un périphérique audio s’est arrêté. Vérifiez sa connexion et les choix dans Réglages.')
        if self.last_output_callback is not None and now - self.last_output_callback > CALLBACK_TIMEOUT_SECONDS:
            raise AudioDeviceError('La sortie audio ne fournit plus de données. Reconnexion audio nécessaire.')
        if self.mic_open and self.last_input_callback is not None and now - self.last_input_callback > CALLBACK_TIMEOUT_SECONDS:
            raise AudioDeviceError('Le microphone ne fournit plus de données. Reconnexion audio nécessaire.')

    def attach_wake(self, listener):
        """Start asleep: call before the microphone opens so no PCM leaks out."""
        with self.capture_lock:
            self.wake = listener
            self.asleep = True
        listener.on_wake = self._woke
        listener.start()

    def sleep(self):
        if self.wake is None:
            return
        with self.capture_lock:
            self.asleep = True
            self.input.clear()
        self.woke.clear()
        self.wake.reset()

    def _woke(self, blocks):
        # Listener thread. Speech queued after « Jarvis » goes out first, then
        # the very next capture callback pushes live audio: no gap, no reorder.
        with self.capture_lock:
            if not self.asleep or not self.mic_open:
                return
            self.asleep = False
            for block in blocks:
                self.input.push(block)
        self.woke.set()

    def consume_wake(self):
        if not self.woke.is_set():
            return False
        self.woke.clear()
        return True

    def play_cue(self, kind):
        """Quiet optional tones use this same output and its feedback guard."""
        if kind == "wake":
            # Speech often follows « Jarvis » at once: this blip must not
            # trigger the half-duplex guard that would drop it.
            frequencies = (880,)
        else:
            frequencies = (660, 440) if kind == "muted" else (660, 880)
        samples = array("h")
        count = int(SAMPLE_RATE * 0.065)
        for frequency in frequencies:
            for index in range(count):
                envelope = sin(pi * index / count) ** 2
                samples.append(int(1800 * envelope * sin(2 * pi * frequency * index / SAMPLE_RATE)))
        with self.cue_lock:
            self.cue = samples.tobytes()  # Replace, never accumulate notifications.
            self.cue_guarded = kind != "wake"

    def clear_cue(self):
        with self.cue_lock:
            self.cue = b""

    def levels(self):
        now = self.clock()
        incoming, input_time = self.input_meter
        outgoing, output_time = self.output_meter
        return (incoming if self.mic_open and not self.asleep and not self.input_suppressed and now - input_time < 0.15 else 0.0,
                outgoing if not self.output.closed and now - output_time < 0.15 else 0.0)

    @property
    def input_suppressed(self):
        return self.mic_open and not self.allow_barge_in and self.clock() < self.suppress_until

    def _input_callback(self, data, frames, timing, status):
        self.last_input_callback = self.clock()
        with self.capture_lock:
            if self.mic_open and not self.input_suppressed:
                if self.asleep:
                    self.wake.feed(data)  # Local only; Gemini receives nothing.
                else:
                    self.input.push(data)
                    self.input_meter = (pcm_level(data), self.clock())

    def _output_callback(self, data, frames, timing, status):
        self.last_output_callback = self.clock()
        latency = max(0, timing.outputBufferDacTime - timing.currentTime) + frames / SAMPLE_RATE
        pcm = self.output.read(len(data), latency)
        guarded = True
        if not any(pcm):
            with self.cue_lock:
                cue, self.cue = self.cue[:len(data)], self.cue[len(data):]
                guarded = self.cue_guarded
            if cue:
                pcm = cue + bytes(len(data) - len(cue))
        if self.quiet:pcm = bytes(len(data))
        self.output_meter = (pcm_level(pcm), self.clock())
        if any(pcm) and guarded and not self.allow_barge_in:
            # Half duplex, not acoustic echo cancellation: don't feed Jarvis's
            # own speaker audio back to Gemini. Include hardware latency and
            # a short room echo tail; explicit mute still owns the device.
            with self.capture_lock:
                self.suppress_until = max(self.suppress_until,
                    self.clock() + latency + ECHO_TAIL_SECONDS)
                self.input.clear()
        data[:] = pcm

    def open(self, microphone=True):
        self.default_snapshot=self.read_defaults()
        try:
            self.speaker = self.devices.RawOutputStream(device=self.output_device, samplerate=SAMPLE_RATE,
                channels=1, dtype="int16", blocksize=BLOCK_SAMPLES, callback=self._output_callback)
            self.last_output_callback = self.clock()
            self.speaker.start()
            if microphone:
                self.set_microphone(True)
        except Exception:
            self.close()
            raise

    def set_microphone(self, enabled):
        if enabled:
            self.input.clear()
            try:
                if self.microphone is None:
                    self.microphone = self.devices.RawInputStream(device=self.input_device, samplerate=SAMPLE_RATE,
                        channels=1, dtype="int16", blocksize=BLOCK_SAMPLES, callback=self._input_callback)
                self.last_input_callback = self.clock()
                self.microphone.start()
                self.mic_open = True
            except Exception:
                self.mic_open = False
                if self.microphone is not None:
                    self.microphone.close()
                    self.microphone = None
                raise
        else:
            self.mic_open = False  # Stop capture before asking PortAudio to stop.
            if self.microphone is not None:
                self.microphone.stop()
            self.input.clear()

    def finish_push_to_talk(self):
        # Close the single capture stream first, retain its final queued frames,
        # then send a bounded synthetic silence tail to Gemini's turn detector.
        with self.capture_lock:
            was_open=self.mic_open
            self.mic_open=False
        if self.microphone is not None:self.microphone.stop()
        if was_open:self.input.tail_frames=45

    def close(self):
        self.mic_open = False
        if self.wake is not None:
            self.wake.close()
        self.clear_cue()
        self.input.closed = True
        self.input.clear()
        self.output.closed = True
        self.output.clear_buffer()
        failures = []
        for name in ("microphone", "speaker"):
            stream = getattr(self, name)
            if stream is not None:
                try:
                    stream.abort()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception as error:
                    failures.append(error)
                finally:
                    setattr(self, name, None)
        if failures:
            raise RuntimeError("Audio device cleanup failed") from None
