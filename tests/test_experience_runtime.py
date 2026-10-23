import asyncio
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,Mock
from concurrent.futures import Future
import pytest
from jarvis.desktop.live_runtime import LiveRuntime
from jarvis.desktop.presentation_tools import presentation_tools
from jarvis.desktop.experience_core import UndoLedger
from test_desktop_live_runtime import components,until


def test_quiet_transcripts_are_opt_in_and_never_include_user_words():
    events=[];runtime=LiveRuntime(events.append)
    runtime._conversation(NS(item=NS(id='one',role='assistant',text_content='PRIVATE_REPLY')))
    assert 'PRIVATE_REPLY' not in str(events)
    runtime.set_profile({'quiet':True})
    runtime._conversation(NS(item=NS(id='two',role='assistant',text_content='r'*6000)))
    runtime._conversation(NS(item=NS(id='three',role='user',text_content='PRIVATE_USER_WORDS')))
    texts=[e['text'] for e in events if e['type']=='assistant_text']
    assert len(texts)==1 and len(texts[0])==4000
    assert 'PRIVATE_USER_WORDS' not in str(events)


def test_profile_updates_in_place_and_headphone_interrupt_is_explicit():
    async def scenario():
        c=components();c.assistant.update_instructions=AsyncMock();runtime=LiveRuntime(lambda event:None,factory=lambda:c,prepare=lambda:None)
        runtime.set_profile({'quiet':True,'headphones':True,'tone':'warm','detail':'short'})
        task=asyncio.create_task(runtime.run());await until(lambda:runtime.ready)
        assert c.audio.quiet and c.audio.allow_barge_in
        assert 'chaleureux' in c.assistant.update_instructions.call_args.args[0]
        runtime.agent_state='speaking';runtime._user_changed(NS(new_state='speaking'))
        assert runtime.interrupt_requested.is_set()
        runtime.set_profile({'quiet':False,'headphones':False})
        await until(lambda:not c.audio.quiet and not c.audio.allow_barge_in)
        assert runtime.components is c and not c.session.closed
        runtime.stop();await asyncio.wait_for(task,1)
    asyncio.run(scenario())


def test_desktop_requests_use_registered_guarded_tools_and_sanitize_errors():
    async def scenario():
        events=[];runtime=LiveRuntime(events.append)
        tool=AsyncMock(return_value={'ok':True,'message':'Started'})
        runtime.components=NS(assistant=NS(jarvis_tools=[NS(info=NS(name='run_task'),__call__=tool)]))
        class Tool:
            info=NS(name='run_task')
            async def __call__(self,**kwargs):return await tool(**kwargs)
        runtime.components.assistant.jarvis_tools=[Tool()]
        await runtime._desktop_action('run_task',{'goal':'Read agenda','read_only':True})
        tool.assert_awaited_once_with(goal='Read agenda',read_only=True)
        tool.side_effect=ValueError('PRIVATE_PROVIDER_ERROR')
        await runtime._desktop_action('run_task',{'goal':'Read agenda'})
        assert 'PRIVATE_PROVIDER_ERROR' not in str(events)
        before=tool.await_count;await runtime._desktop_action('send_message',{})
        assert tool.await_count==before and any(e.get('ok') is False for e in events)
    asyncio.run(scenario())


def test_voice_configuration_waits_for_actual_ui_receipt():
    async def scenario():
        def observer(event):event['receipt'].set_result({'ok':True,'voice':'Kore'})
        tool=presentation_tools(NS(presentation_observer=observer))[0]
        result=await tool(voice='Kore',detail='short')
        assert result=={'ok':True,'voice':'Kore'}
        unavailable=presentation_tools(NS(presentation_observer=None))[0]
        assert not (await unavailable(voice='Kore'))['ok']
    asyncio.run(scenario())


def test_undo_uses_safe_mode_guard_and_keeps_original_file(tmp_path):
    from jarvis.live.registry import create_live_registry
    class Memory:
        def log_action(self,*args):pass
    registry=create_live_registry(memory_capability=Memory())
    registry.read_only_mode=True
    tools=registry.livekit_tools()
    old=tmp_path/'old';new=tmp_path/'new';new.write_text('unchanged')
    events=[];runtime=LiveRuntime(events.append)
    runtime.components=NS(assistant=NS(registry=registry,jarvis_tools=tools))
    runtime.undo_ledger.record('move_file',{'ok':True,'state_confirmed':True,'previous_path':str(old),'path':str(new)})
    identifier=next(iter(runtime.undo_ledger.tickets))
    asyncio.run(runtime._desktop_action('undo',{'id':identifier}))
    assert new.exists() and not old.exists() and identifier in runtime.undo_ledger.tickets
    assert not next(e for e in events if e['type']=='desktop_result')['ok']


def test_reminder_undo_refuses_modified_or_imminent_reminder():
    async def scenario():
        future=time.time()+3600;events=[];runtime=LiveRuntime(events.append)
        runtime.undo_ledger.record('set_reminder',{'ok':True,'reminder_id':2,'due_at':future,'recurrence':'none'})
        identifier=next(iter(runtime.undo_ledger.tickets));cancel=AsyncMock(return_value={'ok':True})
        class Tool:
            info=NS(name='cancel_reminder')
            async def __call__(self,**kwargs):return await cancel(**kwargs)
        store=NS(get=Mock(return_value={'status':'pending','due_at':future+5,'recurrence':'none'}))
        runtime.components=NS(assistant=NS(registry=NS(reminder_store=store),jarvis_tools=[Tool()]))
        await runtime._desktop_action('undo',{'id':identifier});cancel.assert_not_awaited()
        store.get.return_value={'status':'pending','due_at':future,'recurrence':'none'}
        await runtime._desktop_action('undo',{'id':identifier});cancel.assert_awaited_once_with(reminder_id=2)
        assert identifier not in runtime.undo_ledger.tickets
    asyncio.run(scenario())


def test_queued_command_does_not_block_audio_controls_and_cleanup_cancels_it():
    async def scenario():
        c=components();started=asyncio.Event()
        class Tool:
            info=NS(name='ask_about_document')
            async def __call__(self,**kwargs):started.set();await asyncio.Event().wait()
        c.assistant.jarvis_tools=[Tool()]
        runtime=LiveRuntime(lambda event:None,factory=lambda:c,prepare=lambda:None)
        runtime.request_action('ask_about_document',{'path':'/example','question':'summary'})
        task=asyncio.create_task(runtime.run());await until(lambda:started.is_set())
        runtime.set_muted(True);await until(lambda:not c.audio.mic_open)
        runtime.stop();await asyncio.wait_for(task,1)
        assert c.session.closed and c.audio.closed
    asyncio.run(scenario())


def test_initial_profile_precedes_session_connection():
    async def scenario():
        c=components();order=[]
        async def profile(instructions):order.append('profile')
        original=c.session.start
        async def start(**kwargs):
            order.append('connection')
            assert order==['profile','connection']
            await original(**kwargs)
        c.assistant.update_instructions=profile;c.session.start=start
        runtime=LiveRuntime(lambda event:None,factory=lambda:c,prepare=lambda:None)
        task=asyncio.create_task(runtime.run());await until(lambda:runtime.ready)
        runtime.stop();await asyncio.wait_for(task,1)
        assert order==['profile','connection']
    asyncio.run(scenario())
