"""Local PCM devices for LiveKit's public AudioInput/AudioOutput interfaces.

Imported only on explicit voice activation. Audio is bounded in RAM, never saved.
PortAudio callbacks never touch Qt or the asyncio session directly.
"""
from __future__ import annotations

import asyncio
from collections import deque
from queue import Empty, Full, Queue
from threading import Lock

from livekit import rtc
from livekit.agents.voice.io import AudioInput, AudioOutput, AudioOutputCapabilities

SAMPLE_RATE = 24000
BLOCK_SAMPLES = 480  # 20 ms, mono PCM16


class MicrophoneInput(AudioInput):
    def __init__(self):
        super().__init__(label="Jarvis microphone")
        self.frames = Queue(maxsize=25)  # At most half a second of speech.
        self.closed = False

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
    def __init__(self, loop, devices=None):
        if devices is None:
            import sounddevice as devices
        self.devices = devices
        self.input = MicrophoneInput()
        self.output = SpeakerOutput(loop)
        self.microphone = None
        self.speaker = None
        self.mic_open = False

    def _input_callback(self, data, frames, timing, status):
        if self.mic_open:
            self.input.push(data)

    def _output_callback(self, data, frames, timing, status):
        latency = max(0, timing.outputBufferDacTime - timing.currentTime) + frames / SAMPLE_RATE
        data[:] = self.output.read(len(data), latency)

    def open(self):
        try:
            self.speaker = self.devices.RawOutputStream(samplerate=SAMPLE_RATE,
                channels=1, dtype="int16", blocksize=BLOCK_SAMPLES, callback=self._output_callback)
            self.speaker.start()
            self.set_microphone(True)
        except Exception:
            self.close()
            raise

    def set_microphone(self, enabled):
        if enabled:
            self.input.clear()
            try:
                if self.microphone is None:
                    self.microphone = self.devices.RawInputStream(samplerate=SAMPLE_RATE,
                        channels=1, dtype="int16", blocksize=BLOCK_SAMPLES, callback=self._input_callback)
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

    def close(self):
        self.mic_open = False
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
