import asyncio
from array import array
from types import SimpleNamespace as NS

import pytest

from jarvis.desktop import live_runtime
from jarvis.desktop.live_runtime import LiveRuntime
from jarvis.desktop.wake_word import (Downsampler, WakeListener, WakeWordDetector, WakeWordUnavailable,
                                      wake_idle_seconds, wake_threshold)

BLOCK = bytes(960)  # 20 ms of 24 kHz PCM16, like the capture callback.


class ScriptedEngine:
    """Stands in for openWakeWord: one score per 80 ms frame, no model, no audio."""
    frame_samples = 1280

    def __init__(self, scores):
        self.scores = list(scores)
        self.frames = []
        self.resets = 0

    def score(self, frame):
        self.frames.append(len(frame))
        return self.scores.pop(0) if self.scores else 0.0

    def reset(self):
        self.resets += 1


def test_downsampler_turns_three_samples_into_two_across_block_edges():
    sampler = Downsampler()
    first = sampler.feed(array("h", [0, 300, 600, 900]).tobytes())  # One sample carried over.
    assert array("h", first).tolist() == [150, 450]
    second = sampler.feed(array("h", [1200, 1500]).tobytes())
    assert array("h", second).tolist() == [1050, 1350]
    assert len(Downsampler().feed(bytes(960))) == 640  # 480 → 320 samples.


def test_detector_fires_once_per_utterance_then_respects_refractory():
    now = [0.0]
    engine = ScriptedEngine([0.1, 0.9, 0.95])
    detector = WakeWordDetector(engine, threshold=0.5, clock=lambda: now[0], refractory=2.0)
    fired = [detector.process(BLOCK) for _ in range(6)]  # 6×20 ms < one 80 ms frame...
    assert fired == [False] * 6 and engine.frames == [2560]  # ...until 1280 samples at 16 kHz.
    results = [detector.process(BLOCK) for _ in range(4)]
    assert results.count(True) == 1 and engine.resets == 1
    engine.scores = [0.99] * 10
    now[0] = 1.0
    assert not any(detector.process(BLOCK) for _ in range(8))  # Still within 2 s.
    now[0] = 3.0
    assert any(detector.process(BLOCK) for _ in range(8))


def test_listener_hands_over_speech_queued_after_the_wake_word():
    woke = []
    detector = NS(process=lambda block: block == b"jarvis", reset=lambda: None)
    listener = WakeListener(detector, on_wake=woke.append)
    for block in (b"bruit", b"jarvis", b"quelle", b"heure"):
        listener.feed(block)
    assert not listener.pump()
    assert listener.pump()
    assert woke == [[b"quelle", b"heure"]] and listener.blocks.empty()


def test_listener_queue_is_bounded_and_drops_oldest_audio():
    listener = WakeListener(NS(process=lambda b: False, reset=lambda: None))
    for index in range(80):
        listener.feed(bytes([index]))
    assert listener.blocks.qsize() == 50 and listener.blocks.get_nowait() == bytes([30])


def test_listener_thread_stops_and_reports_engine_failure():
    def broken(block):
        raise RuntimeError("onnx")
    listener = WakeListener(NS(process=broken, reset=lambda: None))
    listener.start()
    listener.feed(BLOCK)
    for _ in range(100):
        if listener.failed:
            break
        listener.stopped.wait(0.01)
    listener.close()
    assert listener.failed and listener.thread is None


def test_tuning_variables_are_clamped(monkeypatch):
    monkeypatch.setenv("JARVIS_WAKE_THRESHOLD", "5")
    monkeypatch.setenv("JARVIS_WAKE_IDLE_SECONDS", "2")
    assert wake_threshold() == 0.95 and wake_idle_seconds() == 15
    monkeypatch.setenv("JARVIS_WAKE_IDLE_SECONDS", "abc")
    assert wake_idle_seconds() == 45


# --- Audio gate (needs the Live SDK for MicrophoneInput frames) -------------

class FakeStream:
    def __init__(self, **kwargs): self.active = False
    def start(self): self.active = True
    def stop(self): self.active = False
    def abort(self): self.active = False
    def close(self): pass


class RecordingListener:
    def __init__(self):
        self.fed, self.on_wake, self.started, self.closed, self.resets = [], None, False, False, 0
    def feed(self, block): self.fed.append(bytes(block))
    def start(self): self.started = True
    def reset(self): self.resets += 1
    def close(self): self.closed = True


def gate():
    pytest.importorskip("livekit.agents")
    from jarvis.desktop.live_audio import LocalAudio
    audio = LocalAudio(asyncio.new_event_loop(), NS(RawOutputStream=FakeStream, RawInputStream=FakeStream))
    listener = RecordingListener()
    audio.attach_wake(listener)
    audio.open()
    return audio, listener


def test_asleep_capture_reaches_only_the_local_detector():
    audio, listener = gate()
    audio._input_callback(b"\x05\x00" * 480, 480, None, None)
    assert listener.fed and audio.input.frames.qsize() == 0
    assert audio.levels()[0] == 0.0  # No "voice sent" meter while asleep.
    listener.on_wake([b"suite"])
    assert audio.consume_wake() and not audio.consume_wake()
    assert audio.input.frames.get_nowait() == b"suite"
    audio._input_callback(b"\x05\x00" * 480, 480, None, None)
    assert audio.input.frames.qsize() == 1 and len(listener.fed) == 1
    audio.sleep()
    assert audio.asleep and audio.input.frames.qsize() == 0 and listener.resets == 1
    audio.close()
    assert listener.closed


def test_explicit_mute_wins_over_a_late_wake_detection():
    audio, listener = gate()
    audio.set_microphone(False)
    listener.on_wake([b"fuite"])
    assert audio.asleep and not audio.consume_wake() and audio.input.frames.qsize() == 0
    audio._input_callback(BLOCK, 480, None, None)
    assert not listener.fed
    audio.close()


def test_wake_blip_does_not_trigger_half_duplex_but_other_cues_do():
    audio, _ = gate()
    timing = NS(outputBufferDacTime=0.0, currentTime=0.0)
    audio.play_cue("wake")
    audio._output_callback(bytearray(960), 480, timing, None)
    assert not audio.input_suppressed
    audio.play_cue("ready")
    audio._output_callback(bytearray(960), 480, timing, None)
    assert audio.input_suppressed
    audio.close()


# --- Runtime -----------------------------------------------------------------

class WakeSession:
    def __init__(self):
        self.input, self.output = NS(audio=None), NS(audio=None)
        self.handlers, self.replies = {}, []
    def on(self, name, callback): self.handlers[name] = callback
    async def start(self, **kwargs): self.handlers["agent_state_changed"](NS(new_state="listening"))
    def generate_reply(self, **kwargs): self.replies.append(kwargs)
    async def interrupt(self): pass
    async def aclose(self): pass


class WakeAudio:
    def __init__(self):
        self.input = self.output = object()
        self.mic_open = self.asleep = self.closed = False
        self.wake = None
        self.cues, self.woke, self.order = [], False, []
    def attach_wake(self, listener):
        self.order.append("attach"); self.wake = listener; self.asleep = True
    def open(self, microphone=True):
        self.order.append("open"); self.mic_open = microphone
    def set_microphone(self, enabled): self.mic_open = enabled
    def sleep(self): self.asleep = True
    def consume_wake(self):
        woke, self.woke = self.woke, False
        return woke
    def hear_jarvis(self): self.asleep = False; self.woke = True
    def play_cue(self, kind): self.cues.append(kind)
    def clear_cue(self): pass
    def close(self): self.closed = True; self.mic_open = False


class Closeable:
    closed = False
    async def aclose(self): self.closed = True


def wake_runtime(events, listener=None, wake_factory=None):
    c = NS(session=WakeSession(), audio=WakeAudio(), model=Closeable(), assistant=NS(registry=Closeable()))
    options = []
    def factory(**kwargs):
        options.append(kwargs)
        return c
    listener = listener or NS(closed=False, failed=False, close=lambda: None)
    runtime = LiveRuntime(events.append, factory=factory, prepare=lambda: None,
                          wake_factory=wake_factory or (lambda: listener))
    runtime.set_wake_word(True)
    return runtime, c, options


def last_state(events):
    return [e for e in events if e["type"] == "state"][-1]


async def until(predicate):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0.005)
    assert predicate()


def test_wake_session_starts_asleep_silent_and_wakes_with_a_blip_only(monkeypatch):
    async def scenario():
        clock = [1000.0]
        monkeypatch.setattr(live_runtime, "monotonic", lambda: clock[0])
        monkeypatch.setenv("JARVIS_WAKE_IDLE_SECONDS", "30")
        events = []
        runtime, c, options = wake_runtime(events)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        assert options == [{"long_session": True}]
        assert c.audio.order == ["attach", "open"]  # Gate closed before capture starts.
        assert not c.session.replies  # No greeting, no self-introduction.
        assert last_state(events)["standby"] and last_state(events)["state"] == "muted"
        c.audio.hear_jarvis()
        await until(lambda: c.audio.cues == ["wake"])
        await until(lambda: last_state(events)["state"] == "listening" and not last_state(events)["standby"])
        assert not c.session.replies  # The user's own turn continues; Jarvis says nothing.
        clock[0] += 29
        await asyncio.sleep(0.1)
        assert not c.audio.asleep
        runtime._agent_changed(NS(new_state="speaking"))  # Activity resets the idle timer.
        await asyncio.sleep(0.1)
        runtime._agent_changed(NS(new_state="listening"))
        clock[0] += 29
        await asyncio.sleep(0.1)
        assert not c.audio.asleep
        clock[0] += 2
        await until(lambda: c.audio.asleep)
        await until(lambda: last_state(events)["standby"])
        runtime.stop()
        await asyncio.wait_for(task, 1)
    asyncio.run(scenario())


def test_unmute_in_wake_mode_returns_to_standby_not_to_gemini():
    async def scenario():
        events = []
        runtime, c, _ = wake_runtime(events)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        c.audio.hear_jarvis()
        await until(lambda: not last_state(events)["standby"])
        runtime.set_muted(True)
        await until(lambda: not c.audio.mic_open)
        runtime.set_muted(False)
        await until(lambda: c.audio.mic_open)
        assert c.audio.asleep
        runtime.stop()
        await asyncio.wait_for(task, 1)
    asyncio.run(scenario())


def test_missing_detector_fails_closed_before_any_gemini_connection():
    async def scenario():
        events = []
        def unavailable():
            raise WakeWordUnavailable("Mot d’éveil indisponible.")
        runtime, c, options = wake_runtime(events, wake_factory=unavailable)
        await asyncio.wait_for(runtime.run(), 1)
        assert options == [] and not c.audio.order
        assert events[-1]["state"] == "error" and "Mot d’éveil" in events[-1]["message"]
    asyncio.run(scenario())


def test_detector_crash_ends_the_session_instead_of_opening_the_microphone():
    async def scenario():
        events = []
        listener = NS(failed=False, close=lambda: None)
        runtime, c, _ = wake_runtime(events, listener=listener)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        listener.failed = True
        await asyncio.wait_for(task, 1)
        assert c.audio.closed and c.audio.asleep
        assert events[-1]["state"] == "error" and "mot d’éveil" in events[-1]["message"]
    asyncio.run(scenario())


def test_push_to_talk_takes_precedence_over_wake_mode():
    async def scenario():
        events = []
        loaded = []
        runtime, c, options = wake_runtime(events, wake_factory=lambda: loaded.append(1))
        runtime.set_push_to_talk(True)
        runtime.set_muted(True)
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        assert not loaded and options == [{}] and c.audio.order == ["open"]
        runtime.stop()
        await asyncio.wait_for(task, 1)
    asyncio.run(scenario())
