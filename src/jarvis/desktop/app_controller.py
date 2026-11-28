"""Controller: owns the voice session, audio jobs and missions for every desktop view."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from collections import OrderedDict

from jarvis.desktop.app_controller_voice import ControllerVoiceMixin
from jarvis.desktop.app_controller_jobs import ControllerJobsMixin


class Controller(
    ControllerVoiceMixin,
    ControllerJobsMixin,
    QObject,
):
    routine_result = Signal(object)
    notice = Signal(object)
    appearance_requested = Signal()
    appearance_changed = Signal(str)
    changed = Signal()
    audio_levels = Signal(float, float)
    exit_ready = Signal()
    details_requested = Signal()
    mission_details_requested = Signal()
    audio_event = Signal(object)
    devices_changed = Signal()

    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.request_status = ""
        self.quiet_replies = []
        self.undo_tickets = []
        from jarvis.desktop.avatar_dance import AvatarDance
        self.dance = AvatarDance(self)
        self.dance_music = True
        self.backchannel = True
        self.ptt_hotkey_message="Maintenez ⌘⌥Espace, ou Espace lorsque le compagnon a le focus."
        self.ptt_enabled=False
        self.ptt_held=False
        self.wake_enabled = False
        self.wake_standby = False
        self.ptt_timer=QTimer(self);self.ptt_timer.setSingleShot(True);self.ptt_timer.setInterval(45000)
        self.ptt_timer.timeout.connect(self.end_push_to_talk)
        self.avatar_feedback = None
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.setInterval(2200)
        self.feedback_timer.timeout.connect(self.clear_avatar_feedback)
        self.appearance = "nova_bot"
        self.reduced_motion = False
        self.voice_worker = None
        self.selected_voice = "Puck"
        self.session_voice = None
        self.voice_state = "off"
        self.voice_desired=False
        self.recovery_message=""
        self.voice_mic_open = False
        self.input_suppressed = False
        self.voice_error = ""
        self.voice_turns = 0
        self.quit_after_voice = False
        self.sounds_enabled = False
        self.cards = OrderedDict()
        self.activity = OrderedDict()
        self.task = None
        self.missions = OrderedDict()
        self.selected_mission_id = None
        self.mission_history = OrderedDict()
        self.hidden_mission_bilan = None
        self.screen_operations = set()
        self.input_choice = self.output_choice = None
        self.device_config_invalid = False
        self.audio_worker = None
        self.audio_job_kind = None
        self.audio_job_state = "idle"
        self.local_mic_open = False
        self.can_reconnect = False
        self.reconnecting = False
        self.microphone_muted = False
        self.user_stop_requested = False
        self.hotkey_enabled = True
        self.hotkey_active = False
        self.hotkey_message = 'Raccourci local uniquement.'
        self.tool_notice = ""
        self.tool_timer = QTimer(self)
        self.tool_timer.setSingleShot(True)
        self.tool_timer.setInterval(6000)
        self.tool_timer.timeout.connect(self.clear_tool_notice)

    def set_push_to_talk(self,enabled):
        self.end_push_to_talk()
        self.ptt_enabled=bool(enabled)
        if self.voice_worker:self.voice_worker.set_push_to_talk(enabled)
        if enabled and self.voice_worker:
            self.microphone_muted=True;self.voice_worker.set_muted(True)
        self.changed.emit()

    def set_wake_word(self, enabled):
        self.wake_enabled = bool(enabled)
        if self.voice_worker:
            # The local model loads before connecting: applied on the next start.
            self.tool_notice = "Mot d’éveil " + ("activé" if enabled else "désactivé") + " au prochain démarrage du vocal."
            self.tool_timer.start()
        self.changed.emit()

    def begin_push_to_talk(self):
        if not self.ptt_enabled or self.ptt_held or self.demo or self.audio_worker is not None or self.voice_state=='stopping':return
        if self.voice_worker and self.voice_state=='error':return
        self.ptt_held=True;self.ptt_timer.start()
        if not self.voice_worker:self.start_voice()
        if self.voice_worker:
            if self.voice_state=='speaking':self.voice_worker.interrupt()
            self.microphone_muted=False;self.voice_worker.set_muted(False)
        else:
            self.ptt_held=False;self.ptt_timer.stop()
        self.changed.emit()

    def end_push_to_talk(self):
        if not self.ptt_held:return
        self.ptt_held=False;self.ptt_timer.stop();self.microphone_muted=True
        if self.voice_worker:
            self.voice_worker.finish_push_to_talk()
        self.changed.emit()

    def run_routine(self,name):
        if self.demo or not self.voice_worker or self.voice_state in {'starting','stopping','error'}:return False
        accepted = self.voice_worker.run_routine(name)
        if accepted is False:
            self.tool_notice = "File de routines pleine ou session arrêtée. Réessayez après les demandes en cours."
            self.changed.emit()
        return accepted

    def contextual_voice_action(self):
        if self.ptt_enabled:return
        if self.demo or self.audio_worker is not None or self.voice_state in {'starting','stopping'}: return
        if self.voice_worker:
            if self.voice_state=='error': return
            if self.voice_state=='speaking': self.interrupt_voice()
            else: self.toggle_microphone()
        else: self.start_voice()

    def avatar_state(self):
        if self.voice_state == 'error' or self.avatar_feedback == 'error':
            return 'error'
        if self.avatar_feedback and self.voice_state not in {'speaking','thinking'}:return self.avatar_feedback
        if self.voice_state not in {'speaking','thinking'}:
            if any(m.get('status') in {'needs_confirmation','needs_clarification'} for m in self.focus_missions()):return 'waiting'
            if any(m.get('status') in {'running','queued','waiting_dependency'} for m in self.focus_missions()):return 'thinking'
        return self.avatar_feedback if self.voice_state not in {'error', 'speaking', 'thinking'} and self.avatar_feedback else self.voice_state

    def clear_avatar_feedback(self):
        self.avatar_feedback = None
        self.changed.emit()

    def toggle_microphone(self):
        if self.ptt_enabled:return
        if self.voice_worker and self.voice_state not in {"starting", "stopping", "error"}:
            self.microphone_muted = self.voice_mic_open
            self.voice_worker.set_muted(self.microphone_muted)

    def interrupt_voice(self):
        if self.voice_worker and self.voice_state not in {"starting", "stopping", "error"}:
            self.voice_worker.interrupt()

    def announce(self, message):
        """Speak a proactive alert in the open voice session; False when none is open."""
        if self.demo or not self.voice_worker or self.voice_state in {"off", "starting", "stopping", "error"}:
            return False
        return self.voice_worker.announce(message) is not False
