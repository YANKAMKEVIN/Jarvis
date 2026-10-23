"""Explicit Gemini integration probe; fake devices, no microphone or actual speaker.

python scripts/diagnose_experience_live.py --live
Uses one fixed request and the configured Gemini API quota. No Mac tools exist
in this probe's registry, no user text or files are read or printed.
"""
import argparse
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


async def probe():
    from livekit.agents import Agent,AgentSession
    from livekit.plugins import google
    from jarvis.desktop.live_runtime import LiveRuntime,prepare_environment,desktop_turn_detection_config
    from jarvis.desktop.live_audio import LocalAudio
    from jarvis.live.factory import create_assistant_class,create_realtime_model
    from jarvis.live.config import get_live_config
    from jarvis.live.logging import install_livekit_pii_log_filter
    install_livekit_pii_log_filter()
    settings=[];replies=[];states=[];components=[]
    class Registry:
        presentation_observer=None
        def livekit_tools(self):return []
        def set_task_notifier(self,callback):pass
        def set_presentation_observer(self,callback):self.presentation_observer=callback
        async def aclose(self):pass
    class Stream:
        active=False
        def __init__(self,**kwargs):pass
        def start(self):self.active=True
        def abort(self):self.active=False
        def close(self):self.active=False
    def no_microphone(**kwargs):raise AssertionError('Microphone is forbidden in this probe')
    def factory():
        audio=LocalAudio(asyncio.get_running_loop(),NS(RawOutputStream=Stream,RawInputStream=no_microphone))
        assistant=create_assistant_class(Agent,registry_factory=Registry,desktop=True)()
        model=create_realtime_model(google,get_live_config(),realtime_input_config=desktop_turn_detection_config())
        session=AgentSession(llm=model,vad=None,turn_handling={'turn_detection':'realtime_llm','interruption':{'resume_false_interruption':False}})
        result=NS(audio=audio,assistant=assistant,model=model,session=session);components.append(result);return result
    def emit(event):
        if event['type']=='companion_config':
            settings.append(True)
            event['receipt'].set_result({'ok':True,'message':'Réponses courtes enregistrées.'})
        elif event['type']=='assistant_text':replies.append(True)
        elif event['type']=='state':states.append(event['state'])
    runtime=LiveRuntime(emit,factory=factory,prepare=prepare_environment)
    runtime.set_push_to_talk(True);runtime.set_muted(True);runtime.set_profile({'quiet':True,'tone':'warm','detail':'short'})
    async def drain():
        while not runtime.stop_requested.is_set():
            if runtime.ready:components[0].audio._output_callback(bytearray(960),480,NS(outputBufferDacTime=0,currentTime=0),None)
            await asyncio.sleep(.02)
    task=asyncio.create_task(runtime.run());output=asyncio.create_task(drain())
    try:
        deadline=asyncio.get_running_loop().time()+50
        while not runtime.ready and not task.done() and asyncio.get_running_loop().time()<deadline:await asyncio.sleep(.05)
        if runtime.ready:
            components[0].session.generate_reply(instructions='Pour ce test, appelle configure_companion avec detail=short, puis confirme en une courte phrase française.',tool_choice='auto')
            while not (settings and replies) and not task.done() and asyncio.get_running_loop().time()<deadline:await asyncio.sleep(.05)
        return {'ready':runtime.ready,'settings_acknowledged':bool(settings),'quiet_reply_received':bool(replies),'hardware_microphone_opened':False,'hardware_speaker_opened':False,'session_error':'error' in states}
    finally:
        runtime.stop();await asyncio.wait_for(task,15);await output


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live:parser.error('--live is required: this uses the configured Gemini API quota')
    try:
        result=asyncio.run(probe());print(result)
        if not all(result[key] for key in ('ready','settings_acknowledged','quiet_reply_received')) or result['session_error']:raise SystemExit(1)
    except Exception as error:print({'probe_error_type':type(error).__name__});raise SystemExit(1)

if __name__=='__main__':main()
