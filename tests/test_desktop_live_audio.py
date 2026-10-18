import asyncio
from types import SimpleNamespace as NS
import pytest
pytest.importorskip("livekit.agents")
from livekit import rtc
from jarvis.desktop.live_audio import MicrophoneInput, SpeakerOutput, LocalAudio, SAMPLE_RATE


def frame(data=b'\x01\x00' * 480):
    return rtc.AudioFrame(data=data, sample_rate=SAMPLE_RATE, num_channels=1, samples_per_channel=len(data)//2)


def test_input_is_bounded_and_close_ends_stream():
    async def scenario():
        mic = MicrophoneInput()
        for _ in range(50):
            mic.push(bytes(960))
        assert mic.frames.qsize() == 25
        audio = await mic.__anext__()
        assert audio.sample_rate == 24000 and audio.samples_per_channel == 480
        mic.closed = True
        mic.clear()
        with pytest.raises(StopAsyncIteration):
            await mic.__anext__()
    asyncio.run(scenario())


def test_playback_reports_once_and_clears_queued_audio_on_interrupt():
    async def scenario():
        output = SpeakerOutput(asyncio.get_running_loop())
        events = []
        output.on("playback_finished", events.append)
        await output.capture_frame(frame())
        output.flush()
        assert output.read(960, latency=0.03) == bytes(frame().data)
        output.clear_buffer()
        await asyncio.sleep(0.06)
        assert len(events) == 1 and events[0].interrupted
        assert output.read(960) == bytes(960)
        await output.capture_frame(frame())
        output.flush()
        output.read(960)
        await asyncio.sleep(0.01)
        assert len(events) == 2 and not events[-1].interrupted
        assert events[-1].playback_position == pytest.approx(0.02)
    asyncio.run(scenario())


class FakeStream:
    def __init__(self, **kwargs):
        self.active = False
        self.closed = False
    def start(self): self.active = True
    def stop(self): self.active = False
    def abort(self): self.active = False
    def close(self): self.closed = True


def test_mute_discards_samples_and_shutdown_closes_both_devices():
    async def scenario():
        devices = NS(RawOutputStream=FakeStream, RawInputStream=FakeStream)
        audio = LocalAudio(asyncio.get_running_loop(), devices)
        audio.open()
        microphone, speaker = audio.microphone, audio.speaker
        assert audio.mic_open
        audio._input_callback(bytes(960), 480, None, None)
        assert audio.input.frames.qsize() == 1
        audio.set_microphone(False)
        audio._input_callback(bytes(960), 480, None, None)
        assert audio.input.frames.qsize() == 0 and not microphone.active
        audio.close()
        assert not audio.mic_open and microphone.closed and speaker.closed
    asyncio.run(scenario())


def test_failed_device_start_releases_partial_resources():
    class BrokenInput(FakeStream):
        def start(self): raise RuntimeError("denied")
    async def scenario():
        created = []
        def speaker(**kwargs):
            stream = FakeStream()
            created.append(stream)
            return stream
        audio = LocalAudio(asyncio.get_running_loop(), NS(RawOutputStream=speaker, RawInputStream=BrokenInput))
        with pytest.raises(RuntimeError):
            audio.open()
        assert not audio.mic_open and created[0].closed
        assert audio.microphone is None and audio.speaker is None
    asyncio.run(scenario())


def test_speaker_feedback_is_blocked_through_hardware_latency_and_echo_tail():
    async def scenario():
        now = [10.0]
        audio = LocalAudio(asyncio.get_running_loop(),
            NS(RawOutputStream=FakeStream, RawInputStream=FakeStream), clock=lambda: now[0])
        audio.open()
        try:
            audio._input_callback(bytes(960), 480, None, None)
            assert audio.input.frames.qsize() == 1
            await audio.output.capture_frame(frame())
            audio.output.flush()
            timing = NS(outputBufferDacTime=1.1, currentTime=1.0)
            data = bytearray(960)
            audio._output_callback(data, 480, timing, None)
            assert any(data) and audio.input_suppressed
            assert audio.input.frames.empty()  # No stale capture forwarded.
            audio._input_callback(bytes(frame().data), 480, None, None)
            assert audio.input.frames.empty()
            audio.output.clear_buffer()  # Interrupt cannot remove hardware audio.
            now[0] = 10.35
            assert audio.input_suppressed
            now[0] = 10.38
            assert not audio.input_suppressed
            audio._input_callback(bytes(960), 480, None, None)
            assert audio.input.frames.qsize() == 1
            # Output silence must not extend the pause forever.
            audio._output_callback(data, 480, timing, None)
            assert not any(data) and not audio.input_suppressed
            await audio.output.capture_frame(frame())
            audio._output_callback(data, 480, timing, None)
            audio.set_microphone(False)
            now[0] += 1
            audio._input_callback(bytes(960), 480, None, None)
            assert not audio.mic_open and audio.input.frames.empty()
            assert not audio.microphone.active
        finally:
            audio.close()
    asyncio.run(scenario())
