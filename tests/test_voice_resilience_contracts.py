"""Voice controls keep working while tools, playback or input are busy."""
import asyncio
from types import SimpleNamespace as NS
import pytest
from jarvis.desktop.live_runtime import LiveRuntime
from jarvis.desktop.live_audio import LocalAudio, MicrophoneInput
from test_desktop_live_runtime import components, until
from test_desktop_live_audio import FakeStream, frame

@pytest.mark.parametrize('quiet',[False,True])
@pytest.mark.parametrize('headphones',[False,True])
@pytest.mark.parametrize('latency',[0.,.05,.25])
def test_playback_respects_quiet_and_echo_contract(quiet,headphones,latency):
    async def run():
        now=[10.]
        audio=LocalAudio(asyncio.get_running_loop(),NS(RawOutputStream=FakeStream,RawInputStream=FakeStream),clock=lambda:now[0])
        audio.quiet=quiet;audio.allow_barge_in=headphones;audio.open()
        try:
            audio._input_callback(b'\x01\x00'*480,480,None,None)
            await audio.output.capture_frame(frame());audio.output.flush()
            out=bytearray(960)
            audio._output_callback(out,480,NS(outputBufferDacTime=latency,currentTime=0.),None)
            assert bool(any(out)) is (not quiet)
            assert bool(audio.input_suppressed) is (not quiet and not headphones)
            now[0]+=latency+.5
            assert not audio.input_suppressed
            audio.set_microphone(False)
            audio._input_callback(b'\x01\x00'*480,480,None,None)
            assert audio.input.frames.empty()
        finally:audio.close()
    asyncio.run(run())

@pytest.mark.parametrize('initial_muted',[False,True])
@pytest.mark.parametrize('profile',[{}, {'quiet':True}, {'headphones':True}, {'quiet':True,'headphones':True}])
def test_slow_tool_does_not_prevent_mute_interrupt_or_stop(initial_muted,profile):
    async def run():
        c=components();started=asyncio.Event();cancelled=asyncio.Event()
        class Tool:
            info=NS(name='ask_about_document')
            async def __call__(self,**kwargs):
                started.set()
                try:await asyncio.Event().wait()
                finally:cancelled.set()
        c.assistant.jarvis_tools=[Tool()]
        runtime=LiveRuntime(lambda event:None,factory=lambda:c,prepare=lambda:None)
        runtime.set_profile(profile);runtime.set_muted(initial_muted)
        runtime.request_action('ask_about_document',{'path':'/fictional','question':'Résumé'})
        task=asyncio.create_task(runtime.run())
        try:
            await until(started.is_set)
            runtime.set_muted(not initial_muted);await until(lambda:c.audio.mic_open==initial_muted)
            runtime.interrupt();await until(lambda:c.session.interrupts==1)
        finally:runtime.stop();await asyncio.wait_for(task,2)
        assert cancelled.is_set() and c.audio.closed and c.session.closed
    asyncio.run(run())

@pytest.mark.parametrize('buffered',[0,1,24,25,100])
def test_closed_microphone_never_replays_buffered_user_audio(buffered):
    async def run():
        mic=MicrophoneInput()
        for _ in range(buffered):mic.push(b'\x01\x00'*480)
        mic.closed=True;mic.clear()
        with pytest.raises(StopAsyncIteration):await mic.__anext__()
        assert mic.frames.empty()
    asyncio.run(run())
