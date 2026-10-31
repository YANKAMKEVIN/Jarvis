import asyncio
from array import array
from types import SimpleNamespace as NS
import pytest
pytest.importorskip("livekit.agents")
from livekit import rtc
from jarvis.desktop.echo_cancel import (Rechunker, echo_cancel_requested, float_to_pcm16,
                                        pcm16_to_float)
from jarvis.desktop.live_audio import LocalAudio, SAMPLE_RATE


class FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.active = False
        self.closed = False
    def start(self): self.active = True
    def stop(self): self.active = False
    def abort(self): self.active = False
    def close(self): self.closed = True


class FakeEngine:
    """Stands in for VoiceProcessingDevices: same constructors, no Core Audio."""
    def __init__(self, broken_input=False):
        self.broken_input = broken_input
        self.shut = False
        self.streams = []
    def RawOutputStream(self, **kwargs):
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream
    def RawInputStream(self, **kwargs):
        engine = self
        class Input(FakeStream):
            def start(self):
                if engine.broken_input:
                    raise RuntimeError("tap refused")
                super().start()
        stream = Input(**kwargs)
        self.streams.append(stream)
        return stream
    def shutdown(self): self.shut = True


PORTAUDIO = NS(RawOutputStream=FakeStream, RawInputStream=FakeStream)
TIMING = NS(outputBufferDacTime=0, currentTime=0)


def speech():
    data = b'\x01\x00' * 480
    return rtc.AudioFrame(data=data, sample_rate=SAMPLE_RATE, num_channels=1, samples_per_channel=480)


@pytest.mark.parametrize("value,expected", [("1", True), ("oui", True), (" ON ", True),
                                            ("", False), ("0", False), ("non", False)])
def test_echo_cancel_is_opt_in(value, expected):
    assert echo_cancel_requested({"JARVIS_ECHO_CANCEL": value}) is expected
    assert echo_cancel_requested({}) is False


def test_disabled_by_default_uses_portaudio(monkeypatch):
    monkeypatch.delenv("JARVIS_ECHO_CANCEL", raising=False)
    async def scenario():
        audio = LocalAudio(asyncio.get_running_loop(), PORTAUDIO)
        assert audio.echo_cancel_factory is None
        audio.open()
        try:
            assert not audio.echo_cancelled and isinstance(audio.speaker, FakeStream)
        finally:
            audio.close()
    asyncio.run(scenario())


def test_echo_cancel_opens_both_streams_on_one_engine():
    async def scenario():
        engine = FakeEngine()
        audio = LocalAudio(asyncio.get_running_loop(), PORTAUDIO, echo_cancel=lambda: engine)
        audio.open()
        try:
            assert audio.echo_cancelled and audio.mic_open
            assert engine.streams == [audio.speaker, audio.microphone]
            audio.set_microphone(False)
            audio.set_microphone(True)  # Unmute reuses the same engine stream.
            assert len(engine.streams) == 2 and audio.microphone.active
        finally:
            audio.close()
        assert audio.speaker is None and audio.microphone is None
    asyncio.run(scenario())


def test_engine_failure_falls_back_to_half_duplex():
    def broken():
        raise RuntimeError("Voice processing unavailable")
    async def scenario():
        audio = LocalAudio(asyncio.get_running_loop(), PORTAUDIO, echo_cancel=broken)
        audio.open()
        try:
            assert not audio.echo_cancelled and audio.streams is PORTAUDIO
            assert "Voice processing unavailable" in audio.echo_cancel_error
            assert audio.mic_open and isinstance(audio.speaker, FakeStream)
        finally:
            audio.close()
    asyncio.run(scenario())


def test_microphone_failure_on_engine_releases_it_then_falls_back():
    async def scenario():
        engine = FakeEngine(broken_input=True)
        audio = LocalAudio(asyncio.get_running_loop(), PORTAUDIO, echo_cancel=lambda: engine)
        audio.open()
        try:
            assert engine.shut and all(stream.closed for stream in engine.streams[:1])
            assert not audio.echo_cancelled and audio.mic_open
            assert audio.speaker not in engine.streams
        finally:
            audio.close()
    asyncio.run(scenario())


def test_explicit_device_choice_keeps_portaudio():
    async def scenario():
        engine = FakeEngine()
        audio = LocalAudio(asyncio.get_running_loop(), PORTAUDIO, echo_cancel=lambda: engine)
        audio.output_device = 3  # Chosen in Réglages: the engine follows defaults only.
        audio.open()
        try:
            assert not audio.echo_cancelled and engine.streams == []
        finally:
            audio.close()
    asyncio.run(scenario())


def test_echo_cancelled_speech_leaves_the_microphone_open():
    async def scenario():
        audio = LocalAudio(asyncio.get_running_loop(), PORTAUDIO, echo_cancel=FakeEngine)
        audio.open()
        try:
            await audio.output.capture_frame(speech())
            audio.output.flush()
            out = bytearray(960)
            audio._output_callback(out, 480, TIMING, None)
            assert any(out) and not audio.input_suppressed
            audio._input_callback(b'\x05\x00' * 480, 480, None, None)
            assert audio.input.frames.qsize() == 1  # Kevin can talk over Jarvis.
        finally:
            audio.close()
    asyncio.run(scenario())


def test_dance_music_stays_guarded_even_with_echo_cancel():
    async def scenario():
        audio = LocalAudio(asyncio.get_running_loop(), PORTAUDIO, echo_cancel=FakeEngine)
        audio.open()
        try:
            audio.play_music(b'\x10\x00' * 960)
            audio._output_callback(bytearray(960), 480, TIMING, None)
            assert audio.input_suppressed
            audio._input_callback(b'\x05\x00' * 480, 480, None, None)
            assert audio.input.frames.empty()
        finally:
            audio.close()
    asyncio.run(scenario())


def test_fallback_keeps_the_half_duplex_guard():
    def broken():
        raise OSError("no AVFoundation")
    async def scenario():
        audio = LocalAudio(asyncio.get_running_loop(), PORTAUDIO, echo_cancel=broken)
        audio.open()
        try:
            await audio.output.capture_frame(speech())
            audio.output.flush()
            audio._output_callback(bytearray(960), 480, TIMING, None)
            assert audio.input_suppressed
        finally:
            audio.close()
    asyncio.run(scenario())


def test_pcm_conversions_round_trip_and_clip():
    pcm = array("h", [0, 16384, -16384, 32767, -32768]).tobytes()
    back = array("h", float_to_pcm16(pcm16_to_float(pcm)))
    assert list(back) == pytest.approx([0, 16384, -16384, 32767, -32767], abs=1)
    assert list(array("h", float_to_pcm16(array("f", [2.0, -2.0])))) == [32767, -32768]


def test_rechunker_emits_fixed_blocks_and_keeps_the_rest():
    chunks = Rechunker(960)
    assert chunks.feed(bytes(500)) == []
    blocks = chunks.feed(bytes(1500))
    assert [len(block) for block in blocks] == [960, 960] and len(chunks.pending) == 80


@pytest.mark.parametrize("echo_cancelled,interrupts", [(True, True), (False, False)])
def test_talking_over_jarvis_interrupts_only_when_echo_is_cancelled(echo_cancelled, interrupts):
    from jarvis.desktop.live_runtime import LiveRuntime
    runtime = LiveRuntime(lambda event: None)
    runtime.components = NS(audio=NS(echo_cancelled=echo_cancelled))
    runtime.agent_state = "speaking"
    runtime._user_changed(NS(new_state="speaking"))
    assert runtime.interrupt_requested.is_set() is interrupts


def test_desktop_env_file_may_enable_echo_cancel(tmp_path, monkeypatch):
    import os
    from jarvis.desktop import live_runtime
    # A private environment: whatever prepare_environment sets is discarded.
    monkeypatch.setattr(os, "environ", {"HOME": str(tmp_path), "GOOGLE_API_KEY": "test"})
    config = tmp_path / "Library/Application Support/Jarvis"
    config.mkdir(parents=True)
    (config / "desktop.env").write_text("JARVIS_ECHO_CANCEL=1\n")
    live_runtime.prepare_environment()
    assert echo_cancel_requested()
