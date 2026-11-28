"""Roomless Gemini Live session, controlled from the desktop worker thread."""
from __future__ import annotations

import asyncio
import os
import traceback
import time
from collections import deque
from pathlib import Path
from threading import Event
from time import monotonic
from queue import Empty, Full, Queue
from types import SimpleNamespace
import uuid

from jarvis.activity import log_event
from jarvis.live.confirmation import note_user_turn_from_text
from jarvis.desktop.presentation import project_activity, project_task
from jarvis.desktop.devices import AudioDeviceError
from jarvis.desktop.live_setup import (  # noqa: F401 -- re-exported
    VoiceSetupError,
    setup_failure,
    setup_step,
    prepare_environment,
    preload_live_plugins,
    DEFAULT_TURN_SILENCE_MS,
    turn_silence_ms,
    desktop_turn_detection_config,
    introduced_marker_path,
    session_greeting,
    long_session_options,
    create_components,
)
from jarvis.desktop.live_runtime_controls import LiveRuntimeControlsMixin
from jarvis.desktop.live_runtime_events import LiveRuntimeEventsMixin


ANNOUNCEMENT_MAX_AGE = 120.0
ANNOUNCEMENT_GAP = 5.0  # lets the agent state leave "listening" before the next one


class LiveRuntime(
    LiveRuntimeControlsMixin,
    LiveRuntimeEventsMixin,
):
    def __init__(self, emit, factory=create_components, prepare=prepare_environment, wake_factory=None):
        self.emit = emit
        self.wake_factory = wake_factory
        self.wake_mode_requested = Event()
        self.wake_listener = None
        self.factory = factory
        self.voice_override = None
        from jarvis.desktop.experience_core import TurnProgress, UndoLedger
        self.turn_progress = TurnProgress()
        self.undo_ledger = UndoLedger()
        self.desktop_requests = Queue(maxsize=10)
        self.desktop_task = None
        self.profile = {}
        self.profile_dirty = True
        self.service_calls = {}
        self.result_recorder = None
        self.prepare = prepare
        self.stop_requested = Event()
        self.mute_requested = Event()
        self.ptt_release_requested = Event()
        self.ptt_mode_requested=Event()
        self.interrupt_requested = Event()
        self.ready = False
        self.failed = False
        self.agent_state = "listening"
        self.user_state = "listening"
        self.components = None
        self.interruption_task = None
        self.seen_items = deque(maxlen=512)
        self.sounds_requested = Event()
        self.cancel_task_requested = Event()
        self.task_cancellations = Queue(maxsize=32)
        self.observed_tools = set()
        self.activity_serial=0
        # Mission results have no other spoken channel: they never expire.
        self.task_announcements = deque()
        self.last_task_snapshot = None
        self.input_choice = self.output_choice = None
        self.closing = False
        self.announcements = Queue(maxsize=32)
        self.routine_requests=Queue(maxsize=10)

    def _admit(self, queue, value):
        if self.stop_requested.is_set() or self.closing:
            return False
        try:
            queue.put_nowait(value)
        except Full:
            return False
        return True

    async def _announce_task(self,instructions):
        while len(self.task_announcements) >= 10:
            if self.stop_requested.is_set() or self.closing:
                return False
            await asyncio.sleep(.02)
        if self.stop_requested.is_set() or self.closing:
            return False
        self.task_announcements.append((monotonic(),instructions))
        return True

    def announce(self, message):
        """Queue a proactive alert; spoken only once Jarvis is idle, never over a reply."""
        return self._admit(self.announcements, (monotonic(), message))

    def _registry_activity(self, event):
        self.activity_serial+=1
        self.turn_progress.response()
        if event.get('phase') == 'started':
            label = project_activity(event['tool'], None, event['id'], 'started')['label']
            self.service_calls[event['id']] = [label, monotonic(), False]
        else:self.service_calls.pop(event['id'], None)
        if event.get("phase") == "result":
            before = tuple(self.undo_ledger.tickets)
            self.undo_ledger.record(event.get("tool"), event.get("result"))
            if tuple(self.undo_ledger.tickets) != before:
                self.emit({"type":"undo_available", "tickets":self.undo_ledger.summaries()})
        self.observed_tools.add(event['tool'])
        from jarvis.desktop.experience_core import ACTION_LABELS
        projected = project_activity(event['tool'], event.get('result'), event['id'], event['phase'])
        projected['label'] = ACTION_LABELS.get(event['tool'], projected['label'])
        self.emit(projected)
        if event.get('phase') == 'result' and self.profile.get('history'):
            from jarvis.desktop.result_history import ResultRecorder,archive_receipt
            if self.result_recorder is None:self.result_recorder=ResultRecorder(on_error=lambda:self.emit({"type":"desktop_result","ok":False,"message":"Stockage indisponible : certains résultats n’ont pas pu être archivés. Les cartes de la session restent disponibles."}))
            row=archive_receipt(event['tool'],event['id'],event.get('result'),projected)
            if row and not self.result_recorder.submit(row):
                self.emit({'type':'desktop_result','ok':False,'message':'Historique occupé : ce résultat n’a pas été archivé. Les cartes restent disponibles dans la session.'})

    async def _start(self):
        c = self.components
        task = asyncio.create_task(c.session.start(agent=c.assistant, record=False))
        try:
            while not task.done() and not self.stop_requested.is_set():
                await asyncio.wait({task}, timeout=0.05)
            if self.stop_requested.is_set():
                return False
            await task
            return True
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def run(self):
        phase = "setup"
        error_message = None
        caught_audio_error=None
        try:
            if self.stop_requested.is_set():
                return
            setup_step("environment", self.prepare)
            wake = self.wake_mode_requested.is_set() and not self.ptt_mode_requested.is_set()
            if wake:
                # Load locally before any Gemini connection exists.
                self.wake_listener = await asyncio.to_thread(self._load_wake_listener)
                if self.stop_requested.is_set():
                    return
            options = {}
            if self.voice_override is not None:
                options["voice"] = self.voice_override
            if wake:
                options["long_session"] = True
            self.components = self.factory(**options)
            c = self.components
            phase = "audio"
            if self.input_choice is not None or self.output_choice is not None:
                c.audio.configure_devices(self.input_choice, self.output_choice)
            if hasattr(c.assistant.registry, "set_presentation_observer"):
                c.assistant.registry.set_presentation_observer(self.emit)
            if hasattr(c.assistant.registry, "set_activity_observer"):
                c.assistant.registry.set_activity_observer(self._registry_activity)
            if hasattr(c.assistant.registry,"set_task_notifier"):
                c.assistant.registry.set_task_notifier(self._announce_task)
            c.session.input.audio = c.audio.input
            c.session.output.audio = c.audio.output
            c.session.on("agent_state_changed", self._agent_changed)
            c.session.on("user_state_changed", self._user_changed)
            c.session.on("conversation_item_added", self._conversation)
            c.session.on("user_input_transcribed", self._user_transcribed)
            c.session.on("error", self._error)
            c.session.on("function_tools_executed", self._tools_executed)
            c.session.on("close", self._closed)
            # Set initial instructions before LiveKit creates its realtime session.
            # Updating during connection can restart Gemini and lose the first turn.
            await self._apply_profile()
            phase = "connection"
            started = await asyncio.wait_for(self._start(), timeout=30)
            if not started or self.stop_requested.is_set():
                return
            phase = "audio"
            if self.wake_listener is not None:
                c.audio.attach_wake(self.wake_listener)  # Asleep before capture starts.
            c.audio.open(microphone=not self.mute_requested.is_set())  # Never briefly reopen a muted microphone.
            self.ready = True
            sounds = self.sounds_requested.is_set()
            if sounds:
                c.audio.play_cue("ready")
            self.state("muted" if self.mute_requested.is_set() or self._standby() else "listening")
            phase = "session"
            from jarvis.live.prompts import INSIGHT_ANNOUNCEMENT
            if not self.ptt_mode_requested.is_set() and self.wake_listener is None:
                c.session.generate_reply(instructions=session_greeting())
            suppressed = False
            next_meter = 0.0
            next_task_poll = 0.0
            next_announcement = 0.0
            idle_limit = None
            if self.wake_listener is not None:
                from jarvis.desktop.wake_word import wake_idle_seconds
                idle_limit = wake_idle_seconds()
            last_activity = monotonic()
            while not self.stop_requested.is_set():
                if self.profile_dirty:await self._apply_profile()
                progress = self.turn_progress.poll(self.agent_state, self.user_state, bool(getattr(c.audio, "input_suppressed", False)))
                if progress:self.emit(progress)
                if self.agent_state == 'listening' and self.user_state != 'speaking':
                    for call in self.service_calls.values():
                        if not call[2] and monotonic()-call[1]>=10:
                            call[2]=True
                            self.emit({'type':'request_progress','stage':'service_waiting',
                                'message':call[0]+' · service en attente. Les détails restent disponibles dans l’activité.'})
                if self.desktop_task is None or self.desktop_task.done():
                    try:name, arguments = self.desktop_requests.get_nowait()
                    except Empty:pass
                    else:self.desktop_task = asyncio.create_task(self._desktop_action(name, arguments))
                if hasattr(c.audio, 'check_health'):
                    c.audio.check_health()
                if sounds != self.sounds_requested.is_set():
                    sounds = self.sounds_requested.is_set()
                    if not sounds:
                        c.audio.clear_cue()
                now = asyncio.get_running_loop().time()
                try:routine=self.routine_requests.get_nowait()
                except Empty:pass
                else:await self._launch_routine(routine)
                if self.cancel_task_requested.is_set():
                    self.cancel_task_requested.clear()
                    tasks = getattr(c.assistant.registry, 'tasks', None)
                    # Yield back to audio controls even if a producer keeps
                    # replenishing the queue while cancellations are processed.
                    for _ in range(32):
                        try:
                            task_id = self.task_cancellations.get_nowait()
                        except Empty:
                            break
                        if tasks is not None:
                            tasks.cancel(task_id) if task_id is not None else tasks.cancel()
                if now >= next_task_poll:
                    self._task_progress()
                    next_task_poll = now + 0.25
                if now >= next_meter:
                    incoming, outgoing = c.audio.levels() if hasattr(c.audio, "levels") else (0.0, 0.0)
                    self.emit({"type": "audio_level", "input": incoming, "output": outgoing})
                    next_meter = now + 0.1
                current_suppression = bool(getattr(c.audio, "input_suppressed", False))
                if current_suppression != suppressed:
                    suppressed = current_suppression
                    self.state(self.presentation_state())
                if self.ptt_release_requested.is_set():
                    self.ptt_release_requested.clear()
                    if self.mute_requested.is_set() and c.audio.mic_open:
                        if hasattr(c.audio,'finish_push_to_talk'): c.audio.finish_push_to_talk()
                        else:c.audio.set_microphone(False)
                        self.state(self.presentation_state())
                if idle_limit is not None:
                    if getattr(self.wake_listener, "failed", False):
                        raise VoiceSetupError("Le mot d’éveil local s’est arrêté. Relancez le vocal.", stage="wake_word")
                    if c.audio.consume_wake():
                        last_activity = monotonic()
                        log_event("wake", "hey_jarvis")
                        c.audio.play_cue("wake")  # Always: the only sign Jarvis heard you.
                        self.state(self.presentation_state())
                    elif c.audio.mic_open and not c.audio.asleep:
                        if self.agent_state != "listening" or self.user_state == "speaking":
                            last_activity = monotonic()
                        elif monotonic() - last_activity >= idle_limit:
                            c.audio.sleep()
                            if sounds:
                                c.audio.play_cue("muted")
                            self.state(self.presentation_state())
                wanted = not self.mute_requested.is_set()
                if wanted != c.audio.mic_open:
                    if wanted and idle_limit is not None:
                        c.audio.sleep()  # Unmuting returns to local standby, not to Gemini.
                    c.audio.set_microphone(wanted)
                    if sounds:
                        c.audio.play_cue("ready" if wanted else "muted")
                    self.state(self.presentation_state())
                if now >= next_announcement and self._can_announce():
                    instructions = None
                    if self.task_announcements:
                        _, instructions = self.task_announcements.popleft()
                    else:
                        try:
                            queued_at, message = self.announcements.get_nowait()
                        except Empty:
                            pass
                        else:
                            # A stale alert is dropped: the tray notification carried it.
                            if monotonic() - queued_at <= ANNOUNCEMENT_MAX_AGE:
                                instructions = INSIGHT_ANNOUNCEMENT.format(message=message)
                    if instructions is not None:
                        c.session.generate_reply(instructions=instructions)
                        next_announcement = now + ANNOUNCEMENT_GAP
                if self.interrupt_requested.is_set():
                    self.interrupt_requested.clear()
                    if self.interruption_task is None or self.interruption_task.done():
                        try:
                            self.interruption_task = asyncio.ensure_future(c.session.interrupt())
                            self.interruption_task.add_done_callback(self._consume_interruption)
                        except RuntimeError:
                            pass  # Speech may already have finished.
                await asyncio.sleep(0.05)
            if self.failed:
                error_message = "La session Gemini s’est interrompue. Vérifiez la connexion, la clé et le modèle, puis relancez le vocal."
        except (VoiceSetupError, AudioDeviceError) as error:
            caught_audio_error=error
            error_message = str(error)
        except Exception:
            error_message = {
                "setup": "Le vocal n’a pas pu être préparé. Vérifiez les dépendances et les autorisations macOS.",
                "connection": "Connexion Gemini impossible. Vérifiez la clé, le modèle et l’accès Internet.",
                "audio": "Micro ou sortie audio indisponible. Vérifiez les périphériques et l’autorisation Microphone dans les réglages macOS.",
                "session": "La session vocale a rencontré un problème. Vérifiez la connexion et les périphériques audio.",
            }[phase]
        finally:
            self.closing = True
            self.ready = False
            if self.wake_listener is not None:
                self.wake_listener.close()  # Idempotent; audio.close may also do it.
            self.emit({"type": "audio_level", "input": 0.0, "output": 0.0})
            c = self.components
            if c is not None:
                # Cut capture/playback before any potentially slow tool cleanup.
                try:
                    c.audio.close()
                except Exception:
                    error_message = "La fermeture audio a rencontré un problème. Vérifiez les périphériques avant de relancer."
                self.state("stopping")
            if self.desktop_task is not None:
                self.desktop_task.cancel()
                await asyncio.gather(self.desktop_task, return_exceptions=True)
            if self.result_recorder is not None:
                await asyncio.to_thread(self.result_recorder.close)
            if c is not None:
                if self.interruption_task is not None:
                    self.interruption_task.cancel()
                    await asyncio.gather(self.interruption_task, return_exceptions=True)
                try:
                    await c.assistant.registry.aclose()
                    self._task_progress()
                except Exception:
                    error_message = error_message or "Une tâche vocale n’a pas pu être fermée correctement. Vérifiez son résultat avant de réessayer."
                if hasattr(c.assistant.registry, "set_presentation_observer"):
                    c.assistant.registry.set_presentation_observer(None)
                if hasattr(c.assistant.registry, "set_activity_observer"):
                    c.assistant.registry.set_activity_observer(None)
                for close in (c.session.aclose, c.model.aclose):
                    try:
                        await close()
                    except Exception:
                        error_message = error_message or "La session vocale n’a pas pu être fermée correctement. Vérifiez les actions en cours."
            if self.failed and not error_message:
                error_message = "La connexion Gemini s’est interrompue. Vérifiez la clé, le modèle et Internet."
            final = {"type": "state", "state": "error" if error_message else "off",
                     "mic_open": False, "message": error_message or ""}
            if error_message:
                final["retryable"] = phase in {"connection", "session"} or (phase=="audio" and isinstance(caught_audio_error,AudioDeviceError))
            self.emit(final)
