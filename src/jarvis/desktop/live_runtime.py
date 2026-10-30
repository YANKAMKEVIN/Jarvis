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

from jarvis.desktop.presentation import project_activity, project_task
from jarvis.desktop.devices import AudioDeviceError


class VoiceSetupError(Exception):
    """A safe, user-facing setup error; never includes provider exception text."""

    def __init__(self, message, stage="configuration", error_type=None, frames=()):
        super().__init__(message)
        self.stage = stage
        self.error_type = error_type
        self.frames = frames


def setup_failure(stage, error):
    names = {"environment": "configuration d’environnement", "sdk_import": "import du SDK",
             "logging": "journalisation", "audio_import": "chargement audio",
             "macos_tools": "outils macOS", "gemini_model": "modèle Gemini",
             "agent_session": "session LiveKit", "wake_word": "mot d’éveil local"}
    frames = tuple(f"{Path(frame.filename).name}:{frame.lineno} ({frame.name})"
                   for frame in traceback.extract_tb(error.__traceback__)[-5:])
    return VoiceSetupError(
        f"Le vocal bloque à l’étape « {names[stage]} » ({type(error).__name__}). "
        f"Code : {stage}. Lancez python scripts/diagnose_desktop_voice.py --worker.",
        stage=stage, error_type=type(error).__name__, frames=frames,
    )


def setup_step(stage, callback):
    try:
        return callback()
    except VoiceSetupError:
        raise
    except Exception as error:
        raise setup_failure(stage, error) from None


def prepare_environment():
    try:
        from dotenv import dotenv_values
    except ImportError:
        raise VoiceSetupError("Installez le vocal : python -m pip install -e '.[desktop,live]'") from None
    allowed = {"GOOGLE_API_KEY", "JARVIS_GEMINI_LIVE_MODEL", "JARVIS_GEMINI_LIVE_VOICE",
               "JARVIS_GEMINI_LIVE_TEMPERATURE", "JARVIS_VISION_ENABLED",
               "JARVIS_PLANNER_BACKEND", "JARVIS_PLANNER_MODEL", "JARVIS_GEMINI_PLANNER_MODEL",
               "JARVIS_PLANNER_NUM_CTX", "JARVIS_PLANNER_TIMEOUT", "JARVIS_LLM_MODEL"}
    # Explicit terminal env wins, then the user's desktop config, then repo .env.
    for path in (Path.home() / "Library/Application Support/Jarvis/desktop.env",
                 Path(__file__).resolve().parents[3] / ".env"):
        if path.is_file():
            for key, value in dotenv_values(path, interpolate=False).items():
                if key in allowed and value is not None:
                    os.environ.setdefault(key, value)
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        raise VoiceSetupError("Clé Gemini manquante. Ajoutez GOOGLE_API_KEY dans le fichier .env du projet "
                              "ou dans ~/Library/Application Support/Jarvis/desktop.env, puis réessayez.")


def preload_live_plugins():
    """Register LiveKit plugins on the main thread, before any voice worker.

    GooglePlugin registers itself at import and LiveKit explicitly rejects
    registration on background threads. This opens no devices or connection.
    """
    try:
        from livekit.plugins import google  # noqa: F401
    except (ImportError, OSError):
        raise VoiceSetupError("Dépendances Live indisponibles. Installez python -m pip install -e '.[desktop,live]'.") from None
    except Exception as error:
        raise setup_failure("sdk_import", error) from None


DEFAULT_TURN_SILENCE_MS = 1100


def turn_silence_ms():
    """Silence that ends a turn; JARVIS_TURN_SILENCE_MS tunes it in the field."""
    try:
        value = int(os.environ.get("JARVIS_TURN_SILENCE_MS", DEFAULT_TURN_SILENCE_MS))
    except ValueError:
        return DEFAULT_TURN_SILENCE_MS
    return min(max(value, 400), 3000)


def desktop_turn_detection_config():
    """Let the user pause to think mid-sentence without Jarvis taking the turn."""
    from google.genai import types
    return types.RealtimeInputConfig(automatic_activity_detection=types.AutomaticActivityDetection(
        disabled=False,
        start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
        prefix_padding_ms=300,
        silence_duration_ms=turn_silence_ms(),
    ))


def introduced_marker_path():
    return Path(os.environ.get("JARVIS_INTRODUCED_PATH")
                or Path.home() / "Library/Application Support/Jarvis/introduced")


def session_greeting():
    """Introduce Jarvis once ever; afterwards only a short welcome back."""
    from jarvis.live.prompts import LIVE_SESSION_GREETING, LIVE_SESSION_WELCOME_BACK
    marker = introduced_marker_path()
    if marker.exists():
        return LIVE_SESSION_WELCOME_BACK
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass  # Worst case Jarvis introduces itself again next launch.
    return LIVE_SESSION_GREETING


def long_session_options():
    """Wake-word sessions idle for hours: let Gemini slide its context window
    and resume across server GoAway resets instead of hitting the 15 min cap."""
    from google.genai import types
    return {"context_window_compression": types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()),
            "session_resumption": types.SessionResumptionConfig()}


def create_components(voice=None, long_session=False):
    try:
        from livekit.agents import Agent, AgentSession
        from livekit.plugins import google
        from jarvis.desktop.live_audio import LocalAudio
        from jarvis.live.config import get_live_config
        from jarvis.live.factory import create_assistant_class, create_realtime_model
        from jarvis.live.logging import install_livekit_pii_log_filter
    except (ImportError, OSError):
        raise VoiceSetupError("Dépendances audio indisponibles. Installez python -m pip install -e '.[desktop,live]'.") from None
    except Exception as error:
        raise setup_failure("sdk_import", error) from None
    setup_step("logging", install_livekit_pii_log_filter)
    try:
        config = get_live_config()
        if voice is not None:
            from dataclasses import replace
            config = replace(config, voice=voice)
    except (ValueError, TypeError):
        raise VoiceSetupError("Configuration Gemini invalide. Vérifiez le modèle, la voix et la température.") from None
    audio = setup_step("audio_import", lambda: LocalAudio(asyncio.get_running_loop()))
    assistant = setup_step("macos_tools", lambda: create_assistant_class(Agent, desktop=True)())
    model = setup_step("gemini_model", lambda: create_realtime_model(google, config,
        realtime_input_config=desktop_turn_detection_config(),
        **(long_session_options() if long_session else {})))
    # Gemini handles turn detection. No inference service or LiveKit room/token.
    session = setup_step("agent_session", lambda: AgentSession(llm=model, vad=None, turn_handling={
        "turn_detection": "realtime_llm",
        "interruption": {"resume_false_interruption": False},
    }))
    return SimpleNamespace(model=model, session=session,
        assistant=assistant, audio=audio)


ANNOUNCEMENT_MAX_AGE = 120.0
ANNOUNCEMENT_GAP = 5.0  # lets the agent state leave "listening" before the next one


class LiveRuntime:
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

    def set_profile(self, profile):
        self.profile = dict(profile)
        self.profile_dirty = True

    def request_action(self, name, arguments):
        return self._admit(self.desktop_requests, (name, dict(arguments)))

    async def _apply_profile(self):
        from jarvis.desktop.experience_core import profile_instructions
        from jarvis.live.prompts import LIVE_SYSTEM_PROMPT
        self.profile_dirty = False
        c = self.components
        c.audio.quiet = bool(self.profile.get("quiet"))
        c.audio.allow_barge_in = bool(self.profile.get("headphones"))
        if hasattr(c.assistant, "update_instructions"):
            await c.assistant.update_instructions(LIVE_SYSTEM_PROMPT + "\n" + profile_instructions(self.profile))

    async def _desktop_action(self, name, arguments):
        from jarvis.desktop.experience_core import DesktopActionError
        allowed = {"run_task", "run_macro", "morning_briefing", "describe_screen", "ask_about_screen",
                   "ask_about_document", "extract_document_actions", "compare_documents",
                   "save_task_procedure", "run_procedure", "move_file", "cancel_reminder"}
        ticket = None
        consent_token = None
        try:
            if name == "undo":
                try:ticket = self.undo_ledger.validate(arguments.get("id"))
                except ValueError as error:raise DesktopActionError(str(error)) from None
                if ticket.get('kind')=='reminder':
                    row=await asyncio.to_thread(self.components.assistant.registry.reminder_store.get,ticket['reminder_id'])
                    if not row or row['status']!='pending' or row['due_at']!=ticket['due_at'] or row['recurrence']!=ticket['recurrence'] or row['due_at']<=time.time()+5:
                        raise DesktopActionError('Le rappel est imminent, modifié ou déjà traité. Aucune annulation effectuée.')
                    name,arguments='cancel_reminder',{'reminder_id':ticket['reminder_id']}
                else:name, arguments = "move_file", {"source":ticket["new"], "destination":ticket["old"]}
                self.undo_ledger.undoing = True
            elif name in {"move_file", "cancel_reminder"}:
                raise DesktopActionError("Utilisez une commande explicite ou une annulation vérifiée.")
            if name not in allowed: raise DesktopActionError("Commande indisponible.")
            tool = next(tool for tool in self.components.assistant.jarvis_tools if tool.info.name == name)
            if name in {'ask_about_document','compare_documents','extract_document_actions'}:
                from jarvis.document_consent import REMOTE_DOCUMENT_PERMISSION
                consent=arguments.pop('_remote_allowed',None)
                if consent is not None and not isinstance(consent,bool):raise DesktopActionError('Autorisation de document invalide.')
                consent_token=REMOTE_DOCUMENT_PERMISSION.set(consent)
            result = await tool(**arguments)
            if ticket and result.get("ok"):
                self.undo_ledger.tickets.pop(ticket["id"], None)
            self.emit({"type":"desktop_result", "tool":name, "ok":bool(result.get("ok")),
                       "message":result.get("message", "Résultat disponible dans l’activité.")})
        except asyncio.CancelledError: raise
        except DesktopActionError as error:
            self.emit({"type":"desktop_result", "tool":name, "ok":False, "message":str(error)})
        except Exception:
            self.emit({"type":"desktop_result", "tool":name, "ok":False, "message":"Commande indisponible. Consultez l’activité puis réessayez."})
        finally:
            if consent_token is not None:
                from jarvis.document_consent import REMOTE_DOCUMENT_PERMISSION
                REMOTE_DOCUMENT_PERMISSION.reset(consent_token)
            self.undo_ledger.undoing = False
            self.emit({"type":"undo_available", "tickets":self.undo_ledger.summaries()})

    def set_voice(self, voice):
        from jarvis.desktop.voices import VOICE_IDS
        if voice not in VOICE_IDS:
            raise ValueError("Unknown desktop voice")
        if self.components is not None:
            raise RuntimeError("Voice is fixed for this session")
        self.voice_override = voice

    def set_devices(self, input_choice, output_choice):
        self.input_choice, self.output_choice = input_choice, output_choice

    def set_sounds(self, enabled):
        self.sounds_requested.set() if enabled else self.sounds_requested.clear()

    def cancel_task(self, task_id=None):
        accepted = self._admit(self.task_cancellations, task_id)
        if accepted:
            self.cancel_task_requested.set()
        return accepted

    def stop(self):
        self.stop_requested.set()

    def set_muted(self, muted):
        self.mute_requested.set() if muted else self.mute_requested.clear()

    def set_push_to_talk(self,enabled):
        self.ptt_mode_requested.set() if enabled else self.ptt_mode_requested.clear()

    def set_wake_word(self, enabled):
        """Applies at session start: the local model must load before connecting."""
        self.wake_mode_requested.set() if enabled else self.wake_mode_requested.clear()

    def _load_wake_listener(self):
        from jarvis.desktop.wake_word import WakeWordUnavailable, create_wake_listener
        try:
            return (self.wake_factory or create_wake_listener)()
        except WakeWordUnavailable as error:
            # Fail closed: never fall back to an always-open Gemini microphone.
            raise VoiceSetupError(str(error), stage="wake_word") from None

    def finish_push_to_talk(self):
        self.mute_requested.set()
        self.ptt_release_requested.set()

    def interrupt(self):
        self.interrupt_requested.set()

    def run_routine(self,name):
        return isinstance(name,str) and 0<len(name)<=80 and self._admit(self.routine_requests, name)

    async def _launch_routine(self,name):
        # Invoke the exact tool already registered with the agent, including its
        # journal and safe-mode guard. Rebuilding tools would replace TaskManager.
        before=self.activity_serial
        try:
            tool=next(t for t in self.components.assistant.jarvis_tools if t.info.name=='run_macro')
            result=await tool(name)
        except Exception:result={'ok':False,'message':'Routine locale indisponible.'}
        if self.activity_serial==before:
            self.emit(project_activity('run_macro',result,uuid.uuid4().hex))
        self.emit({'type':'routine_result','name':name,'ok':bool(result.get('ok')),'reason':result.get('error_code','')})
        self._task_progress()

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

    def state(self, state):
        audio = self.components.audio if self.components else None
        self.emit({"type": "state", "state": state, "mic_open": bool(audio and audio.mic_open),
                   "input_suppressed": bool(audio and getattr(audio, "input_suppressed", False)),
                   "standby": self._standby()})

    def _standby(self):
        audio = self.components.audio if self.components else None
        return bool(audio and audio.mic_open and getattr(audio, "asleep", False))

    def presentation_state(self):
        if self.agent_state in {'speaking','thinking'}:return self.agent_state
        # Standby looks like a muted avatar; the "standby" flag tells the UI why.
        return 'muted' if self.mute_requested.is_set() or self._standby() else self.agent_state

    def _agent_changed(self, event):
        self.agent_state = event.new_state
        if self.agent_state in {"thinking","speaking"}:self.turn_progress.response()
        if self.ready and not self.stop_requested.is_set():
            self.state(self.presentation_state())

    def _user_changed(self, event):
        previous = self.user_state
        self.user_state = event.new_state
        if previous == "speaking" and self.user_state != "speaking":
            self.emit(self.turn_progress.received())
        if self.user_state == "speaking" and self.agent_state == "speaking" and self.profile.get("headphones"):
            self.interrupt_requested.set()

    def _can_announce(self):
        """Idle agent, user not mid-sentence, push-to-talk key released."""
        return (self.agent_state == "listening" and self.user_state != "speaking"
                and (not self.ptt_mode_requested.is_set() or self.mute_requested.is_set()))

    def _conversation(self, event):
        item = event.item
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", "")
        if role in {"user", "assistant"} and isinstance(text, str) and text.strip():
            item_id = getattr(item, "id", None)
            if item_id:
                if item_id in self.seen_items:
                    return
                self.seen_items.append(item_id)
            if role == "user":self.emit(self.turn_progress.received())
            else:
                self.turn_progress.response()
                if self.profile.get("quiet"):
                    self.emit({"type":"assistant_text", "text":text[:4000]})
            # Conversation words stay private except opt-in quiet replies in RAM.
            self.emit({"type": "transcript", "role": role,
                       "interrupted": bool(getattr(item, "interrupted", False))})

    def _error(self, event):
        if not self.closing and not self.stop_requested.is_set() and not getattr(event.error, "recoverable", False):
            self.failed = True
            self.stop_requested.set()

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

    def _tools_executed(self, event):
        for call, output in zip(event.function_calls, event.function_call_outputs):
            if call.name in self.observed_tools:
                continue  # Already received directly from the registry, including planner tools.
            activity_id = getattr(call, 'call_id', None) or uuid.uuid4().hex
            self.emit(project_activity(call.name, output.output, activity_id,
                                       'error' if output.is_error else 'result'))

    def _task_progress(self):
        registry = self.components.assistant.registry
        tasks = getattr(registry, 'tasks', None)
        if tasks is not None and (hasattr(tasks, 'progress') or hasattr(tasks, 'presentations')):
            if hasattr(tasks, 'presentations'):
                snapshot = {'type': 'missions', 'missions': [project_task(item) for item in tasks.presentations()]}
            else:
                snapshot = project_task(tasks.presentation() if hasattr(tasks, 'presentation') else tasks.progress())
            if snapshot is not None and snapshot != self.last_task_snapshot:
                self.last_task_snapshot = snapshot
                self.emit(snapshot)

    def _closed(self, event):
        if not self.closing and not self.stop_requested.is_set():
            self.failed = True
            self.stop_requested.set()

    @staticmethod
    def _consume_interruption(task):
        if not task.cancelled():
            task.exception()  # Consume races with a speech that already ended.

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

