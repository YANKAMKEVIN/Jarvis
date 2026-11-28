"""Voice session lifecycle and the events it reports to the views."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime

from jarvis.desktop.presentation import STATUS_TEXT


class ControllerVoiceMixin:
    """Voice session lifecycle and the events it reports to the views. Mixed into Controller."""

    def start_voice(self, reconnect=None,_automatic=False):
        if self.demo or self.voice_worker is not None or self.audio_worker is not None:
            return
        if self.device_config_invalid:
            self.voice_state, self.voice_error = 'error', 'Choix audio enregistré invalide. Sélectionnez vos périphériques dans Réglages.'
            self.changed.emit()
            return
        self.voice_desired=True
        if hasattr(self,'recovery') and not _automatic:self.recovery.manual_start()
        reconnect = self.can_reconnect if reconnect is None else reconnect
        self.reconnecting = bool(reconnect)
        self.can_reconnect = False
        self.user_stop_requested = False
        if not reconnect:
            self.microphone_muted = self.ptt_enabled and not self.ptt_held
        from jarvis.desktop.live_runtime import VoiceSetupError, preload_live_plugins
        self.voice_state, self.voice_error = "starting", ""
        self.voice_turns = 0
        self.request_status = ""
        self.undo_tickets = []
        if not reconnect:
            self.cards.clear()
            self.activity.clear()
            self.task = None
            self.missions.clear()
            self.selected_mission_id = None
            self.mission_history.clear()
        self.screen_operations.clear()
        self.tool_timer.stop()
        self.tool_notice = ""
        self.changed.emit()
        try:
            preload_live_plugins()
        except VoiceSetupError as error:
            self.voice_state, self.voice_error = "error", str(error)
            self.changed.emit()
            return
        from jarvis.desktop.live_worker import LiveWorker
        worker = LiveWorker(self)
        self.voice_worker = worker
        self.session_voice = self.selected_voice
        if hasattr(worker, "set_voice"):
            worker.set_voice(self.session_voice)
        if hasattr(self, "experience") and hasattr(worker,"set_profile"):
            worker.set_profile(self.experience.options.profile())
        if self.ptt_enabled:worker.set_push_to_talk(True)
        elif self.wake_enabled and hasattr(worker, "set_wake_word"):worker.set_wake_word(True)
        if self.input_choice is not None or self.output_choice is not None:
            worker.set_devices(self.input_choice, self.output_choice)
        if self.microphone_muted:
            worker.set_muted(True)
        if self.sounds_enabled:
            worker.set_sounds(True)
        self.voice_mic_open = False
        self.input_suppressed = False
        worker.event.connect(self.voice_event)
        worker.finished.connect(lambda: self.voice_finished(worker))
        self.changed.emit()
        worker.start()

    def stop_voice(self):
        self.voice_desired=False
        self.end_push_to_talk()
        self.user_stop_requested = True
        self.can_reconnect = False
        if self.voice_worker is not None:
            self.voice_state = "stopping"
            self.voice_worker.stop()
        self.changed.emit()

    def voice_event(self, event):
        kind = event.get("type")
        if kind == "companion_config" and hasattr(self, "experience"):
            self.experience.configure(event);return
        if kind == "request_progress":
            self.request_status = event.get("message", "")
            self.tool_notice = self.request_status
            self.tool_timer.start()
            self.changed.emit();return
        if kind == "undo_available":
            previous={row['id'] for row in self.undo_tickets}
            self.undo_tickets=event['tickets']
            new=[row for row in self.undo_tickets if row['id'] not in previous]
            if new:self.notice.emit({'key':'undo:'+new[0]['id'],'text':'Action réversible · une annulation est disponible.','destination':'undo'})
            self.changed.emit();return
        if kind == "assistant_text":
            if hasattr(self, "experience") and self.experience.options.quiet:
                self.quiet_replies.append(event["text"][:4000]);self.quiet_replies = self.quiet_replies[-5:]
                self.notice.emit({"key":"reply:"+str(self.voice_turns),"text":"Nouvelle réponse écrite disponible","destination":"experience"})
                self.changed.emit()
            return
        if kind == "desktop_result":
            self.request_status = event.get("message", "Résultat disponible.")[:500]
            self.tool_notice = self.request_status;self.tool_timer.start()
            self.changed.emit();return
        if event.get("type") == "avatar_dance":
            if event.get("action") == "stop":
                self.dance.stop()
            elif not self.dance.start():
                self.tool_notice = "Danse indisponible : choisissez un personnage et activez les animations."
                self.tool_timer.start()
                self.changed.emit()
            return
        if event.get('type')=='routine_result':
            self.routine_result.emit(event)
            if not event.get('ok'):
                self.tool_notice='Routine refusée : mode lecture seule.' if event.get('reason')=='read_only_mode' else 'La routine n’a pas pu démarrer. Consultez l’activité.'
                self.tool_timer.start()
                self.notice.emit({'key':'routine:error:'+event.get('reason',''),'text':self.tool_notice,'destination':'details'})
                self.changed.emit()
            return
        if event.get('type') in {'activity', 'tool_receipt', 'task_progress'}:
            status = event.get('status')
            # 'received' is what a tool that succeeded without a state check reports.
            if status in {'success', 'received', 'completed', 'done', 'verified', 'error', 'failed'}:
                self.avatar_feedback = 'error' if status in {'error', 'failed'} else 'success'
                self.feedback_timer.start()
        if event.get('type') == 'activity':
            if event.get('screen'):
                if event['status'] == 'running':
                    self.screen_operations.add(event['id'])
                else:
                    self.screen_operations.discard(event['id'])
            now = datetime.now().strftime('%H:%M:%S')
            self.request_status = event['label'] + ' · ' + STATUS_TEXT.get(event['status'], event['status'])
            self.activity[event['id']] = {'label': event['label'], 'status': event['status'], 'time': now}
            self.activity.move_to_end(event['id'])
            while len(self.activity) > 30:
                self.activity.popitem(last=False)
            if event.get('card'):
                item = {**event['card'], 'time': now}
                self.cards[item['kind']] = item
                self.cards.move_to_end(item['kind'])
                while len(self.cards) > 4:
                    self.cards.popitem(last=False)
            self.tool_notice = f"{event['label']} · {STATUS_TEXT.get(event['status'], 'Résultat reçu')}"
            self.tool_timer.start()
            self.changed.emit()
            return
        if event.get('type') == 'missions':
            for item in event['missions']:
                if item:
                    self.mission_notice(item,self.missions.get(item['id'],{}).get('status'))
            for mission in event['missions']:
                if mission and mission.get('status') in {'completed', 'failed'} and self.missions.get(mission['id'], {}).get('status') != mission['status']:
                    self.avatar_feedback = 'success' if mission['status'] == 'completed' else 'error'
                    self.feedback_timer.start()
            self.missions = OrderedDict((m['id'], m) for m in event['missions'] if m is not None)
            active = [m for m in self.missions.values() if m["status"] in {"queued", "waiting_dependency", "paused", "running", "cancelling", "needs_confirmation", "needs_clarification"}]
            chosen = next((m for m in active if m['id'] == self.selected_mission_id), None)
            self.task = chosen or (active[0] if active else next(reversed(self.missions.values()), None))
            self.selected_mission_id = self.task['id'] if self.task else None
            self.mission_history = OrderedDict((m['id'], m) for m in self.missions.values()
                if m is not self.task and m['status'] not in {'queued', 'waiting_dependency', 'paused', 'running', 'cancelling', 'needs_confirmation', 'needs_clarification'})
            while len(self.mission_history) > 4:
                self.mission_history.popitem(last=False)
            self.changed.emit()
            return
        if event.get('type') == 'task_progress':
            self.mission_notice(event,self.task.get('status') if self.task and self.task['id']==event['id'] else None)
            if self.task and self.task['id'] != event['id']:
                previous = dict(self.task)
                if previous['status'] in {'running', 'cancelling'}:
                    previous['status'] = 'unknown'
                self.mission_history[previous['id']] = previous
                while len(self.mission_history) > 4:
                    self.mission_history.popitem(last=False)
            self.task = event
            self.changed.emit()
            return
        if event.get("type") == "tool_receipt":
            if event.get('status')=='confirmation':
                self.notice.emit({'key':'confirmation:'+event.get('label',''), 'text':'J’attends votre accord vocal', 'destination':'details'})
            states = {"received": "Résultat reçu", "confirmation": "Accord vocal attendu",
                      "error": "L’outil signale un problème"}
            self.tool_notice = f"{event['label']} · {states.get(event.get('status'), 'Résultat reçu')}"
            self.tool_timer.start()
            self.changed.emit()
            return
        if event.get("type") == "audio_level":
            self.audio_levels.emit(event.get("input", 0.0), event.get("output", 0.0))
            return
        if event.get("type") == "transcript":
            # Only a counter enters the UI: no transcript, chat message, draft,
            # or spoken phrase is submitted to another executor.
            if event.get("role") == "user":
                self.voice_turns += 1
                self.changed.emit()
            return
        if event.get("type") == "state":
            state = event["state"]
            if self.voice_state != "stopping" or state in {"stopping", "error", "off"}:
                self.voice_state = state
            self.voice_mic_open = event.get("mic_open", False)
            self.input_suppressed = event.get("input_suppressed", False)
            self.wake_standby = event.get("standby", False)
            self.voice_error = event.get("message", "")
            if state == 'error':
                self.notice.emit({'key':'voice:error:'+self.voice_error,'text':'Connexion vocale interrompue · voir les détails','destination':'settings'})
                self.can_reconnect = bool(event.get('retryable')) and not self.user_stop_requested
            if state in {'listening', 'muted', 'speaking', 'thinking'}:
                self.reconnecting = False
            if state in {'off', 'error'}:
                self.screen_operations.clear()
                for entry in self.activity.values():
                    if entry['status'] == 'running':
                        entry['status'] = 'unknown'
                for mission in self.mission_list():
                    if mission['status'] in {'queued', 'waiting_dependency', 'paused', 'running', 'cancelling'}:
                        mission['status'] = 'unknown'
            self.changed.emit()

    def voice_finished(self, worker):
        if self.voice_worker is worker:
            self.voice_worker = None
            self.session_voice = None
            self.undo_tickets = []
            self.audio_levels.emit(0.0, 0.0)
            self.voice_mic_open = False
            self.input_suppressed = False
            self.wake_standby = False
            if self.voice_state != "error":
                self.voice_state = "off"
            self.changed.emit()
        worker.deleteLater()
        if self.quit_after_voice:
            self.exit_ready.emit()
