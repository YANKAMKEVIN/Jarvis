"""Thread-safe controls the desktop UI calls on the running voice session."""
from __future__ import annotations

import asyncio
import time
import uuid

from jarvis.desktop.live_setup import VoiceSetupError
from jarvis.desktop.presentation import project_activity


class LiveRuntimeControlsMixin:
    """Thread-safe controls the desktop UI calls on the running voice session. Mixed into LiveRuntime."""

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

    def play_dance_music(self, seconds):
        """Loop under the avatar dance, through the voice output and its
        feedback guard. Without an open session there is nothing to play on."""
        audio = self.components.audio if self.components else None
        if audio is None or not hasattr(audio, "play_music"):
            return False
        from jarvis.desktop.dance_music import dance_track
        from jarvis.desktop.live_audio import SAMPLE_RATE
        audio.play_music(dance_track(seconds, SAMPLE_RATE))
        return True

    def stop_dance_music(self):
        audio = self.components.audio if self.components else None
        if audio is not None and hasattr(audio, "stop_music"):
            audio.stop_music()

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
