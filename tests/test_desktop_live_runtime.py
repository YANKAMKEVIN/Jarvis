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

    def open(self):
        self.opened = self.mic_open = True
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
