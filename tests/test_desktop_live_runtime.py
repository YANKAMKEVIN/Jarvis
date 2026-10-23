import asyncio
from types import SimpleNamespace as NS

from jarvis.desktop.live_runtime import LiveRuntime, VoiceSetupError


class FakeSession:
    def __init__(self, mode="ok"):
        self.mode = mode
        self.input, self.output = NS(audio=None), NS(audio=None)
        self.handlers = {}
        self.closed = False
        self.interrupts = 0

    def on(self, name, callback):
        self.handlers[name] = callback

    async def start(self, **kwargs):
        assert kwargs["record"] is False
        if self.mode == "blocked":
            await asyncio.Event().wait()
        if self.mode == "failure":
            raise RuntimeError("SECRET_PROVIDER_PAYLOAD")
        self.handlers["agent_state_changed"](NS(new_state="listening"))

    def generate_reply(self, **kwargs):
        for role, text in (("user", "Bonjour"), ("assistant", "Bonsoir !")):
            self.handlers["conversation_item_added"](NS(item=NS(role=role, text_content=text, interrupted=False)))

    async def interrupt(self):
        self.interrupts += 1

    async def aclose(self):
        self.closed = True


class FakeAudio:
    def __init__(self, failure=False):
        self.input, self.output = object(), object()
        self.mic_open = self.opened = self.closed = False
        self.failure = failure
        self.cues = []
        self.cue_cleared = False

    def play_cue(self, kind):
        self.cues.append(kind)

    def clear_cue(self):
        self.cue_cleared = True

    def open(self, microphone=True):
        self.opened = True
        self.mic_open = microphone
        if self.failure:
            raise RuntimeError("PRIVATE_AUDIO_DETAILS")

    def set_microphone(self, enabled):
        self.mic_open = enabled

    def close(self):
        self.closed = True
        self.mic_open = False


class FakeCloseable:
    def __init__(self, fail=False):
        self.closed = False
        self.fail = fail

    async def aclose(self):
        self.closed = True
        if self.fail:
            raise RuntimeError("SECRET_CLOSE_PAYLOAD")


def components(mode="ok", audio_failure=False, close_failure=False):
    return NS(session=FakeSession(mode), audio=FakeAudio(audio_failure),
              model=FakeCloseable(), assistant=NS(registry=FakeCloseable(close_failure)))


async def until(predicate):
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0.005)
    assert predicate()


def test_voice_lifecycle_mute_interrupt_transcripts_and_cleanup():
    async def scenario():
        events = []
        c = components()
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        assert any(e.get("mic_open") for e in events)
        assert not c.audio.cues
        assert [e["role"] for e in events if e["type"] == "transcript"] == ["user", "assistant"]
        runtime.set_muted(True)
        await until(lambda: not c.audio.mic_open)
        runtime.set_muted(False)
        await until(lambda: c.audio.mic_open)
        runtime.interrupt()
        await until(lambda: c.session.interrupts == 1)
        runtime.stop()
        await asyncio.wait_for(task, 1)
        assert c.audio.closed and c.model.closed and c.session.closed and c.assistant.registry.closed
        assert events[-1] == {"type": "state", "state": "off", "mic_open": False, "message": ""}
    asyncio.run(scenario())


def test_stopping_during_connection_never_opens_microphone():
    async def scenario():
        c = components(mode="blocked")
        events = []
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: bool(c.session.handlers))
        runtime.stop()
        await asyncio.wait_for(task, 1)
        assert not c.audio.opened
        assert c.audio.closed and c.model.closed and c.session.closed
        assert not any(e.get("mic_open") for e in events)
        assert events[-1]["state"] == "off"
    asyncio.run(scenario())


def test_failures_always_release_devices_and_never_echo_secrets():
    async def scenario():
        for kwargs in ({"mode": "failure"}, {"audio_failure": True}, {"close_failure": True}):
            c = components(**kwargs)
            events = []
            runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
            task = asyncio.create_task(runtime.run())
            if kwargs.get("close_failure"):
                await until(lambda: runtime.ready)
                runtime.stop()
            await asyncio.wait_for(task, 1)
            assert c.audio.closed and c.model.closed and c.session.closed
            assert events[-1]["state"] == "error" and not events[-1]["mic_open"]
            assert "SECRET" not in str(events) and "PRIVATE_AUDIO" not in str(events)
    asyncio.run(scenario())


def test_stop_before_start_skips_setup_and_fatal_close_reports_error():
    async def scenario():
        events = []
        runtime = LiveRuntime(events.append, prepare=lambda: (_ for _ in ()).throw(AssertionError()))
        runtime.stop()
        await runtime.run()
        assert events[-1]["state"] == "off"
        c = components()
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        c.session.handlers["close"](NS(error=RuntimeError("PRIVATE")))
        await task
        assert events[-1]["state"] == "error"
    asyncio.run(scenario())


def test_missing_setup_is_actionable_and_never_creates_devices():
    def missing():
        raise VoiceSetupError("Clé Gemini manquante.")
    events = []
    runtime = LiveRuntime(events.append, prepare=missing,
                          factory=lambda: (_ for _ in ()).throw(AssertionError()))
    asyncio.run(runtime.run())
    assert events[-1]["state"] == "error"
    assert events[-1]["message"] == "Clé Gemini manquante."


def test_stop_closes_microphone_even_while_interruption_is_pending():
    async def scenario():
        c = components()
        async def delayed_interrupt():
            c.session.interrupts += 1
            await asyncio.Event().wait()
        c.session.interrupt = delayed_interrupt
        events = []
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        runtime.interrupt()
        await until(lambda: c.session.interrupts == 1)
        runtime.stop()
        await asyncio.wait_for(task, 1)
        assert c.audio.closed and not c.audio.mic_open
        assert events[-1]['state'] == 'off'
    asyncio.run(scenario())


def test_setup_stage_errors_report_location_without_provider_payload():
    from jarvis.desktop.live_runtime import setup_step
    def failing():
        raise TypeError('SECRET_API_KEY_AND_PROVIDER_PAYLOAD')
    try:
        setup_step('agent_session', failing)
    except VoiceSetupError as error:
        assert error.stage == 'agent_session' and error.error_type == 'TypeError'
        assert 'SECRET' not in str(error)
        assert 'SECRET' not in str(error.frames)
        assert any('failing' in frame for frame in error.frames)
    else:
        raise AssertionError('Expected stage failure')


def test_turn_notifications_omit_words_and_deduplicate_ids_only():
    events = []
    runtime = LiveRuntime(events.append)
    def event(item_id):
        return NS(item=NS(id=item_id, role="user", text_content="PRIVATE_WORDS"))
    runtime._conversation(event("same-id"))
    runtime._conversation(event("same-id"))
    runtime._conversation(event("new-id"))  # A deliberate repeated phrase is valid.
    assert len([e for e in events if e["type"] == "transcript"]) == 2
    assert all(e["role"] == "user" and "text" not in e for e in events if e["type"] == "transcript")
    assert "PRIVATE_WORDS" not in str(events)
    assert "PRIVATE" not in str(events)


def test_suppression_changes_are_reported_without_closing_microphone():
    async def scenario():
        c = components()
        events = []
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        c.audio.input_suppressed = True
        await until(lambda: any(e.get("input_suppressed") for e in events))
        assert c.audio.mic_open
        c.audio.input_suppressed = False
        await until(lambda: events[-1].get("input_suppressed") is False)
        runtime.stop()
        await asyncio.wait_for(task, 1)
    asyncio.run(scenario())


def test_tool_receipts_are_based_on_real_results_and_omit_private_data():
    events = []
    runtime = LiveRuntime(events.append)
    calls = [NS(name='open_app', arguments='PRIVATE_APP'), NS(name='set_reminder'),
             NS(name='open_file'), NS(name='unknown_PRIVATE_NAME')]
    outputs = [NS(is_error=False, output='{"ok": true, "secret": "PRIVATE_TOKEN"}'),
               NS(is_error=False, output='{"requires_confirmation": true, "token": "PRIVATE_TOKEN"}'),
               NS(is_error=False, output='{"ok": false, "error": "PRIVATE_ERROR"}'),
               NS(is_error=True, output='PRIVATE_PROVIDER_PAYLOAD')]
    runtime._tools_executed(NS(function_calls=calls, function_call_outputs=outputs))
    assert [e['status'] for e in events] == ['received', 'confirmation', 'error', 'error']
    assert [e['label'] for e in events] == ['Application', 'Rappel', 'Fichier', 'Outil Jarvis']
    assert 'PRIVATE' not in str(events)


def test_optional_cues_follow_ready_and_mute_and_can_be_disabled():
    async def scenario():
        c = components()
        runtime = LiveRuntime(lambda e: None, factory=lambda: c, prepare=lambda: None)
        runtime.set_sounds(True)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        assert c.audio.cues == ['ready']
        runtime.set_muted(True)
        await until(lambda: not c.audio.mic_open)
        assert c.audio.cues[-1] == 'muted'
        runtime.set_sounds(False)
        await until(lambda: c.audio.cue_cleared)
        runtime.set_muted(False)
        await until(lambda: c.audio.mic_open)
        assert c.audio.cues == ['ready', 'muted']
        runtime.stop()
        await asyncio.wait_for(task, 1)
    asyncio.run(scenario())


def test_real_task_progress_bridge_and_cancellation_request_are_separate_from_audio_interrupt():
    async def scenario():
        c = components()
        class Tasks:
            status = 'running'
            requests = 0
            def progress(self): return {'id': 'task-id', 'status': self.status, 'steps': []}
            def cancel(self):
                self.requests += 1
                self.status = 'cancelling'
        c.assistant.registry.tasks = Tasks()
        events = []
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: any(e.get('type') == 'task_progress' for e in events))
        runtime.cancel_task()
        await until(lambda: any(e.get('status') == 'cancelling' for e in events))
        assert c.assistant.registry.tasks.requests == 1 and c.session.interrupts == 0
        c.assistant.registry.tasks.status = 'cancelled'
        await until(lambda: any(e.get('status') == 'cancelled' for e in events))
        runtime.stop()
        await asyncio.wait_for(task, 1)
    asyncio.run(scenario())


def test_multi_mission_bridge_preserves_each_cancellation_identifier():
    async def scenario():
        c = components()
        class Tasks:
            requests = []
            def presentations(self):
                return [{'id': key, 'objective': key, 'status': 'running', 'steps': []} for key in ['first', 'second']]
            def cancel(self, task_id): self.requests.append(task_id)
        c.assistant.registry.tasks = Tasks()
        events = []
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: any(e.get('type') == 'missions' for e in events))
        runtime.cancel_task('second')
        runtime.cancel_task('first')
        await until(lambda: c.assistant.registry.tasks.requests == ['second', 'first'])
        snapshot = next(e for e in events if e.get('type') == 'missions')
        assert [m['id'] for m in snapshot['missions']] == ['first', 'second']
        assert c.session.interrupts == 0
        runtime.stop()
        await asyncio.wait_for(task, 1)
    asyncio.run(scenario())


def test_registry_events_are_not_duplicated_by_sdk_receipts():
    events = []
    runtime = LiveRuntime(events.append)
    runtime._registry_activity({'id': 'real-call', 'tool': 'open_app', 'phase': 'started'})
    runtime._registry_activity({'id': 'real-call', 'tool': 'open_app', 'phase': 'result',
                                'result': {'ok': True, 'state_confirmed': True}})
    runtime._tools_executed(NS(function_calls=[NS(name='open_app', call_id='sdk-call')],
                              function_call_outputs=[NS(is_error=False, output='{"ok":true}')]))
    assert [e['status'] for e in events] == ['running', 'verified']
    assert events[0]['id'] == events[1]['id']


def test_reconnect_is_a_fresh_runtime_without_replaying_tools_or_opening_muted_micro():
    async def scenario():
        first = components()
        first_events = []
        runtime = LiveRuntime(first_events.append, factory=lambda: first, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        first.session.handlers['close'](NS(error=None))  # Unexpected closure must be visible.
        await asyncio.wait_for(task, 1)
        assert first_events[-1]['state'] == 'error' and first_events[-1]['retryable']
        assert first.audio.closed and first.session.closed
        second = components()
        second_events = []
        fresh = LiveRuntime(second_events.append, factory=lambda: second, prepare=lambda: None)
        fresh.set_muted(True)
        new_task = asyncio.create_task(fresh.run())
        await until(lambda: fresh.ready)
        assert second is not first and not second.audio.mic_open
        assert not any(e.get('mic_open') for e in second_events)
        assert not any(e['type'] == 'activity' for e in second_events)
        fresh.stop()
        await asyncio.wait_for(new_task, 1)
        assert second_events[-1]['state'] == 'off'
    asyncio.run(scenario())


def test_selected_devices_are_configured_before_connection():
    async def scenario():
        c = components()
        chosen = []
        c.audio.configure_devices = lambda a, b: chosen.append((a, b))
        events = []
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        choice = {'name': 'Mic', 'hostapi': 'Core Audio'}
        runtime.set_devices(choice, None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        assert chosen == [(choice, None)]
        runtime.stop()
        await task
    asyncio.run(scenario())



def test_proactive_alerts_wait_for_idle_and_drop_stale_ones(monkeypatch):
    import jarvis.desktop.live_runtime as live_runtime
    monkeypatch.setattr(live_runtime, "ANNOUNCEMENT_GAP", 0.0)

    async def scenario():
        c = components()
        replies = []
        greeting = c.session.generate_reply
        c.session.generate_reply = lambda **kw: (replies.append(kw["instructions"]), greeting(**kw))
        runtime = LiveRuntime(lambda e: None, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        assert len(replies) == 1  # greeting only
        c.session.handlers["agent_state_changed"](NS(new_state="speaking"))
        runtime.announce("Le processeur tourne à 95 %.")
        await asyncio.sleep(0.15)
        assert len(replies) == 1  # never over a reply in progress
        c.session.handlers["agent_state_changed"](NS(new_state="listening"))
        await until(lambda: len(replies) == 2)
        assert "Le processeur tourne à 95 %." in replies[1] and "pas une demande" in replies[1]
        runtime.announcements.put((live_runtime.monotonic() - 3600, "vieille alerte"))
        await until(runtime.announcements.empty)  # consumed, then dropped as stale
        assert len(replies) == 2
        runtime.stop()
        await asyncio.wait_for(task, 1)
        assert not any("vieille alerte" in r for r in replies)
    asyncio.run(scenario())

def test_hold_mode_skips_greeting_and_release_before_ready_never_opens_capture():
    async def scenario():
        c=components();calls=[]
        c.session.generate_reply=lambda **kw:calls.append(kw)
        runtime=LiveRuntime(lambda e:None,factory=lambda:c,prepare=lambda:None)
        runtime.set_push_to_talk(True);runtime.set_muted(True);runtime.finish_push_to_talk()
        task=asyncio.create_task(runtime.run());await until(lambda:runtime.ready)
        assert not c.audio.mic_open and not calls
        runtime.set_muted(False);await until(lambda:c.audio.mic_open)
        runtime.finish_push_to_talk();await until(lambda:not c.audio.mic_open)
        runtime.stop();await asyncio.wait_for(task,1)
    asyncio.run(scenario())


def test_routine_request_uses_stored_goal_and_same_task_manager():
    from unittest.mock import Mock
    async def scenario():
        c=components()
        c.assistant.registry.macro_store=NS(get=Mock(return_value={'goal':'Read my agenda'}))
        c.assistant.registry.tasks=NS(start=Mock(return_value={'ok':True,'task_id':'routine-task'}))
        class MacroTool:
            info=NS(name='run_macro')
            async def __call__(self,name):
                row=c.assistant.registry.macro_store.get(name)
                return c.assistant.registry.tasks.start(row['goal'])
        c.assistant.jarvis_tools=[MacroTool()]
        events=[];runtime=LiveRuntime(events.append,factory=lambda:c,prepare=lambda:None)
        runtime.run_routine('Ma journée')
        task=asyncio.create_task(runtime.run())
        await until(lambda:c.assistant.registry.tasks.start.called)
        c.assistant.registry.macro_store.get.assert_called_once_with('Ma journée')
        c.assistant.registry.tasks.start.assert_called_once_with('Read my agenda')
        assert any(e.get('type')=='activity' and e.get('status')=='received' for e in events)
        runtime.stop();await asyncio.wait_for(task,1)
    asyncio.run(scenario())

def test_muted_microphone_does_not_hide_real_thinking_or_speaking_states():
    runtime=LiveRuntime(lambda e:None);runtime.set_muted(True)
    for state in ('thinking','speaking'):
        runtime.agent_state=state;assert runtime.presentation_state()==state
    runtime.agent_state='listening';assert runtime.presentation_state()=='muted'

def test_routine_ui_invokes_existing_guarded_tool_and_cannot_bypass_safe_mode(tmp_path):
    from unittest.mock import Mock
    from jarvis.live.registry import create_live_registry
    from jarvis.macros import MacroStore
    async def scenario():
        store=MacroStore(tmp_path/'routines.db');store.save('Focus','Read agenda')
        registry=create_live_registry(macro_store=store,memory_capability=NS(log_action=lambda *a,**k:None))
        tools=registry.livekit_tools();registry.tasks.start=Mock(return_value={'ok':True,'task_id':'same-manager'})
        c=components();c.assistant.registry=registry;c.assistant.jarvis_tools=tools
        events=[];runtime=LiveRuntime(events.append);runtime.components=c
        await runtime._launch_routine('Focus');registry.tasks.start.assert_called_once_with('Read agenda')
        registry.read_only_mode=True
        await runtime._launch_routine('Focus')
        assert registry.tasks.start.call_count==1
        assert any(e.get('type')=='activity' and e.get('status')=='error' for e in events)
        assert events[-1]['type']=='routine_result' and events[-1]['reason']=='read_only_mode'
        await registry.aclose()
    asyncio.run(scenario())


def test_task_announcement_waits_until_push_to_talk_is_released():
    async def scenario():
        c=components();calls=[];c.session.generate_reply=lambda **kw:calls.append(kw)
        runtime=LiveRuntime(lambda e:None,factory=lambda:c,prepare=lambda:None);runtime.set_push_to_talk(True)
        task=asyncio.create_task(runtime.run());await until(lambda:runtime.ready)
        await runtime._announce_task('Mission completed')
        await asyncio.sleep(.08);assert not calls
        runtime.finish_push_to_talk();await until(lambda:bool(calls))
        assert calls[0]['instructions']=='Mission completed'
        runtime.stop();await asyncio.wait_for(task,1)
    asyncio.run(scenario())


def test_presentation_requests_cross_runtime_bridge_and_detach_on_close():
    async def scenario():
        events = []
        c = components()
        registry = c.assistant.registry
        registry.presentation = None
        registry.set_presentation_observer = lambda observer: setattr(registry, 'presentation', observer)
        runtime = LiveRuntime(events.append, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        registry.presentation({'type':'avatar_dance', 'action':'start'})
        assert events[-1] == {'type':'avatar_dance', 'action':'start'}
        assert c.audio.mic_open  # Presentation does not interrupt the voice session.
        runtime.stop()
        await asyncio.wait_for(task, 1)
        assert registry.presentation is None
    asyncio.run(scenario())


def test_announcements_wait_for_the_user_to_finish_and_task_results_never_expire(monkeypatch):
    import jarvis.desktop.live_runtime as live_runtime
    monkeypatch.setattr(live_runtime, "ANNOUNCEMENT_GAP", 0.0)

    async def scenario():
        c = components()
        calls = []
        c.session.generate_reply = lambda **kw: calls.append(kw["instructions"])
        runtime = LiveRuntime(lambda e: None, factory=lambda: c, prepare=lambda: None)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        calls.clear()  # greeting
        c.session.handlers["user_state_changed"](NS(new_state="speaking"))
        runtime.announce("Disque presque plein.")
        await asyncio.sleep(0.15)
        assert calls == []  # never over the user's sentence
        c.session.handlers["user_state_changed"](NS(new_state="listening"))
        await until(lambda: len(calls) == 1)
        assert "Disque presque plein." in calls[0]
        # A mission result queued long ago is still spoken.
        runtime.task_announcements.append((live_runtime.monotonic() - 3600, "Message prêt pour Marie."))
        await until(lambda: len(calls) == 2)
        assert calls[1] == "Message prêt pour Marie."
        runtime.stop()
        await asyncio.wait_for(task, 1)
    asyncio.run(scenario())


def test_shutdown_closes_microphone_before_waiting_for_desktop_cleanup():
    async def scenario():
        c = components()
        runtime = LiveRuntime(lambda _: None, factory=lambda: c, prepare=lambda: None)
        cleanup_started, release = asyncio.Event(), asyncio.Event()

        async def slow_action():
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await release.wait()

        session = asyncio.create_task(runtime.run())
        try:
            await until(lambda: runtime.ready)
            runtime.desktop_task = asyncio.create_task(slow_action())
            await asyncio.sleep(.01)
            runtime.stop()
            await asyncio.wait_for(cleanup_started.wait(), .5)
            assert c.audio.closed
            assert not c.audio.mic_open
            assert runtime.closing
        finally:
            release.set()
            runtime.stop()
            await asyncio.wait_for(session, 1)
    asyncio.run(scenario())


def test_continuous_cancellation_producer_cannot_starve_mute():
    async def scenario():
        c = components()
        runtime = LiveRuntime(lambda _: None, factory=lambda: c, prepare=lambda: None)
        processed = []
        def cancel(*_):
            processed.append(1)
            if len(processed) < 100:
                runtime.cancel_task('again')
        c.assistant.registry.tasks = NS(cancel=cancel, all=lambda: [])
        task = asyncio.create_task(runtime.run())
        try:
            await until(lambda: runtime.ready)
            runtime.cancel_task('first')
            runtime.set_muted(True)
            await until(lambda: not c.audio.mic_open)
            assert len(processed) == 32
        finally:
            runtime.stop()
            await asyncio.wait_for(task, 1)
    asyncio.run(scenario())
