"""Audio jobs (device tests, voice previews) and mission cards."""
from __future__ import annotations

from jarvis.desktop.devices import valid_choice


class ControllerJobsMixin:
    """Audio jobs (device tests, voice previews) and mission cards. Mixed into Controller."""

    def set_devices(self, input_choice, output_choice):
        if self.voice_worker is not None or self.audio_worker is not None:
            return
        if any(choice is not None and not valid_choice(choice) for choice in (input_choice, output_choice)):
            return
        self.input_choice, self.output_choice = input_choice, output_choice
        self.device_config_invalid = False
        self.devices_changed.emit()
        self.changed.emit()

    def start_voice_preview(self, voice):
        from jarvis.desktop.voices import VOICE_IDS
        if self.demo or self.voice_worker is not None or self.audio_worker is not None or voice not in VOICE_IDS:
            return False
        if self.device_config_invalid:
            self.audio_event.emit({"type": "audio_test", "kind": "voice_preview", "state": "error",
                "message": "Sélectionnez à nouveau votre sortie audio dans Réglages."})
            return False
        from jarvis.desktop.voice_preview import VoicePreview
        worker = VoicePreview(voice, self.output_choice, parent=self)
        self.audio_worker = worker
        self.audio_job_kind = "voice_preview"
        self.audio_job_state = "preparing"
        worker.event.connect(self.handle_audio_event)
        worker.finished.connect(lambda: self.audio_finished(worker))
        self.changed.emit()
        worker.start()
        return True

    def start_audio_job(self, kind):
        if self.demo or self.voice_worker is not None or self.audio_worker is not None:
            return
        if kind not in {'scan', 'microphone', 'speaker'}:
            return
        if self.device_config_invalid and kind != 'scan':
            self.audio_event.emit({'type': 'audio_test', 'state': 'error', 'message': 'Choisissez à nouveau les périphériques avant le test.'})
            return
        from jarvis.desktop.audio_settings import AudioJob
        worker = AudioJob(kind, self.input_choice, self.output_choice, parent=self)
        self.audio_worker = worker
        self.audio_job_kind = kind
        self.audio_job_state = "preparing"
        worker.event.connect(self.handle_audio_event)
        worker.finished.connect(lambda: self.audio_finished(worker))
        self.changed.emit()
        self.audio_event.emit({'type': 'audio_test', 'state': 'preparing',
                               'message': 'Lecture des périphériques…' if kind == 'scan' else 'Préparation du test audio local…'})
        worker.start()

    def handle_audio_event(self, event):
        if event.get('type') == 'audio_test':
            self.audio_job_state = event['state']
            self.local_mic_open = event['state'] == 'microphone'
            self.changed.emit()
        self.audio_event.emit(event)

    def stop_audio_job(self):
        if self.audio_worker is not None:
            self.audio_worker.stop()

    def audio_finished(self, worker):
        if self.audio_worker is worker:
            self.audio_worker = None
            self.audio_job_kind = None
            self.audio_job_state = "idle"
            self.local_mic_open = False
            self.changed.emit()
        worker.deleteLater()
        if self.quit_after_voice:
            self.exit_ready.emit()

    def set_sounds(self, enabled):
        self.sounds_enabled = enabled
        if self.voice_worker:
            self.voice_worker.set_sounds(enabled)

    def clear_cards(self):
        self.cards.clear()
        self.changed.emit()

    def clear_activity(self):
        if (not any(e['status'] == 'running' for e in self.activity.values())
                and not any(m['status'] in {'queued', 'waiting_dependency', 'paused', 'running', 'cancelling'} for m in self.mission_list())):
            self.activity.clear()
            self.mission_history.clear()
            self.missions.clear()
            self.task = None
            self.changed.emit()

    def mission_list(self):
        return list(self.missions.values()) if self.missions else ([self.task] if self.task else [])

    def focus_missions(self):
        active = [m for m in self.mission_list() if m['status'] in {'queued', 'waiting_dependency', 'paused', 'running', 'cancelling', 'needs_confirmation', 'needs_clarification'}]
        if active:
            return sorted(active, key=lambda m: m['id'] != self.selected_mission_id)
        return [self.task] if self.task else []

    def select_mission(self, task_id):
        mission = next((m for m in self.mission_list() if m['id'] == task_id), None)
        if mission is not None:
            self.selected_mission_id = task_id
            self.task = mission
            self.changed.emit()

    def cancel_task(self, task_id=None):
        candidates = [m for m in self.mission_list() if m['status'] in {'queued', 'waiting_dependency', 'paused', 'running'} and (task_id is None or m['id'] == task_id)]
        if len(candidates) != 1 or not self.voice_worker or self.voice_state in {'starting', 'stopping', 'error'}:
            return
        if self.missions:
            accepted = self.voice_worker.cancel_task(candidates[0]['id'])
        else:
            accepted = self.voice_worker.cancel_task()
        if accepted is False:
            self.tool_notice = "Annulation non transmise : file pleine ou session arrêtée. Réessayez."
            self.changed.emit()
        return accepted

    def clear_tool_notice(self):
        self.tool_notice = ""
        self.changed.emit()

    def mission_notice(self,mission,previous):
        status=mission.get('status')
        labels={'completed':'Votre mission est terminée','failed':'Une mission a échoué',
                'needs_confirmation':'Une mission attend votre accord vocal','needs_clarification':'Une mission attend une précision'}
        if status in labels and status!=previous:
            self.notice.emit({'key':f"mission:{mission['id']}:{status}",'text':labels[status], 'mission_id':mission['id']})
