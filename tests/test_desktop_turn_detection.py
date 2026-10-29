"""Exercise turn framing and stalled audio without hardware, recordings or text."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from jarvis.desktop.devices import AudioDeviceError
from jarvis.desktop.live_audio import LocalAudio, CALLBACK_TIMEOUT_SECONDS
from jarvis.desktop.live_runtime import desktop_turn_detection_config, turn_silence_ms
from jarvis.live.config import LiveConfig
from jarvis.live.factory import create_realtime_model
from test_desktop_live_audio import FakeStream, frame


def test_explicit_turn_detection_tolerates_thinking_pauses_and_keeps_pre_speech_context(monkeypatch):
    monkeypatch.delenv('JARVIS_TURN_SILENCE_MS', raising=False)
    config = desktop_turn_detection_config()
    vad = config.automatic_activity_detection
    assert vad.disabled is False
    assert vad.silence_duration_ms == 1100
    assert vad.prefix_padding_ms == 300
    assert vad.start_of_speech_sensitivity.value == 'START_SENSITIVITY_HIGH'
    assert vad.end_of_speech_sensitivity.value == 'END_SENSITIVITY_LOW'
    factory = Mock()
    create_realtime_model(NS(realtime=NS(RealtimeModel=factory)), LiveConfig('test','Puck',.8,'test'), realtime_input_config=config)
    assert factory.call_args.kwargs['realtime_input_config'] is config



@pytest.mark.parametrize('raw, expected', [('800', 800), ('50', 400), ('9000', 3000), ('abc', 1100)])
def test_turn_silence_env_override_is_clamped(monkeypatch, raw, expected):
    monkeypatch.setenv('JARVIS_TURN_SILENCE_MS', raw)
    assert turn_silence_ms() == expected

def test_echo_pause_sends_zeros_then_resumes_real_pcm_and_muting_stops_all_frames():
    async def scenario():
        now = [10.]
        audio = LocalAudio(asyncio.get_running_loop(),
            NS(RawOutputStream=FakeStream, RawInputStream=FakeStream), clock=lambda: now[0])
        audio.open()
        try:
            pcm = bytes(frame().data)
            await audio.output.capture_frame(frame())
            audio._output_callback(bytearray(960), 480, NS(outputBufferDacTime=0, currentTime=0), None)
            audio._input_callback(pcm, 480, None, None)
            assert audio.input.frames.empty()  # Speaker echo is never queued.
            for _ in range(3):
                silent = await asyncio.wait_for(audio.input.__anext__(), .2)
                assert not any(bytes(silent.data)) and silent.samples_per_channel == 480
            now[0] += .5
            audio._input_callback(pcm,480,None,None)
            real = await asyncio.wait_for(audio.input.__anext__(), .2)
            assert bytes(real.data) == pcm
            audio.set_microphone(False)
            audio.suppress_until = now[0] + 1
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(audio.input.__anext__(), .05)
        finally:
            audio.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('stalled', ['microphone', 'speaker'])
def test_callbacks_detect_active_but_stalled_devices(stalled):
    async def scenario():
        now = [10.]
        audio = LocalAudio(asyncio.get_running_loop(),
            NS(RawOutputStream=FakeStream, RawInputStream=FakeStream), clock=lambda: now[0])
        audio.open()
        try:
            audio.check_health()  # A stream gets a startup grace period.
            now[0] += CALLBACK_TIMEOUT_SECONDS + .1
            if stalled == 'microphone':
                audio._output_callback(bytearray(960),480,NS(outputBufferDacTime=0,currentTime=0),None)
            else:
                audio._input_callback(bytes(960),480,None,None)
            assert audio.microphone.active and audio.speaker.active
            with pytest.raises(AudioDeviceError, match='ne fournit plus de données'):
                audio.check_health()
        finally: audio.close()
    asyncio.run(scenario())


def test_real_silence_is_healthy_and_muted_microphone_does_not_trigger_recovery():
    async def scenario():
        now = [10.]
        audio = LocalAudio(asyncio.get_running_loop(),
            NS(RawOutputStream=FakeStream, RawInputStream=FakeStream), clock=lambda: now[0])
        audio.open()
        try:
            for _ in range(6):
                now[0] += 1
                audio._input_callback(bytes(960),480,None,None)
                audio._output_callback(bytearray(960),480,NS(outputBufferDacTime=0,currentTime=0),None)
                audio.check_health()
            audio.set_microphone(False)
            now[0] += CALLBACK_TIMEOUT_SECONDS + .1
            audio._output_callback(bytearray(960),480,NS(outputBufferDacTime=0,currentTime=0),None)
            audio.check_health()
            audio.set_microphone(True)
            audio.check_health()  # Opening the mic resets its grace period.
        finally: audio.close()
    asyncio.run(scenario())
