"""Voice-first desktop companion with explicit, guarded command-palette actions."""
from __future__ import annotations

import signal
import threading
import json
from collections import OrderedDict
from datetime import datetime

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QCheckBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QGraphicsOpacityEffect, QPushButton, QScrollArea, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from jarvis.desktop.audio_settings import AudioSettings
from jarvis.desktop.devices import valid_choice
from jarvis.desktop.hotkey import GlobalHotkey
from jarvis.desktop.tray import TrayControls
from jarvis.desktop.visuals import Orb
from jarvis.desktop.panels import DetailPanel
from jarvis.desktop.mission_panel import MissionDeck
from jarvis.desktop.orb_window import OrbWindow
from jarvis.desktop.companion import CompanionWindow
from jarvis.desktop.presentation import STATUS_TEXT
from jarvis.desktop.surfaces import ControlDock, DragHandle, GlassSurface, OrbTransfer

STYLE = """
QWidget { background: transparent; color: #dce8f6; font-family: '.AppleSystemUIFont', 'Inter', 'DejaVu Sans'; font-size: 13px; }
QMainWindow { background: #0b111b; }
QWidget#shell { background: qradialgradient(cx:0.60, cy:0.36, radius:0.8, fx:0.60, fy:0.36, stop:0 #182c3d, stop:0.42 #0c1826, stop:1 #070e18); }
QLabel#wordmark { color: #e4f3ff; font-size: 18px; font-weight: 600; }
QLabel#greeting { color: #eef7ff; font-size: 26px; font-weight: 500; }
QLabel#intro { color: #94abc1; font-size: 14px; }
QLabel#status { color: #a4cbe7; font-size: 12px; }
QPushButton#quiet { background: transparent; border: 1px solid #304659; color: #a7c1d6; }

QLabel { background: transparent; }
QLabel#eyebrow { color: #7794af; font-size: 10px; font-weight: 600; }
QLabel#title { font-size: 27px; font-weight: 600; }
QLabel#subtitle { color: #91a9c1; font-size: 12px; }
QFrame#sidebar { background: rgba(7, 14, 24, 175); border-right: 1px solid #1d3041; }
QFrame#controlDock { background: rgba(20, 36, 51, 105); border: 1px solid rgba(119, 180, 212, 30); border-radius: 17px; }
QFrame#card { background: rgba(26, 43, 61, 155); border: 1px solid #293e52; border-radius: 16px; }
QPushButton { background: #1a2a3d; border: 1px solid #2b435c; border-radius: 9px; padding: 10px 14px; }
QPushButton:hover { background: #243d57; border-color: #517ca2; }
QPushButton:focus { border: 1px solid #83cfff; }
QPushButton:disabled { color: #647b90; background: #152030; }
QPushButton#primary:hover { background: #b8e4ff; }
QPushButton#primary { background: #82caff; color: #081421; border: 0; font-weight: 600; }
QPushButton#primary:disabled { background: #223247; color: #8096ab; }
QPushButton#nav { text-align: left; background: transparent; border: 0; padding: 13px; color: #91a9c1; }
QPushButton#nav:checked { color: #e0f1ff; background: #22354b; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: #101927; width: 7px; }
QScrollBar::handle:vertical { background: #344c63; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { spacing: 10px; padding: 8px 0; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #52708a; border-radius: 4px; background: #0b1825; }
QCheckBox::indicator:checked { background: #87dcff; border-color: #b5edff; }
QComboBox { background: #132537; border: 1px solid #31495f; border-radius: 8px; padding: 7px; min-height: 18px; }
QComboBox QAbstractItemView { background: #132537; color: #dce8f6; selection-background-color: #29485f; }
QProgressBar { background: #192c3d; border: 1px solid #314b60; border-radius: 4px; min-height: 8px; max-height: 8px; }
QProgressBar::chunk { background: #87d9ff; border-radius: 3px; }
QToolTip { background: #23384f; color: #e1efff; border: 1px solid #527494; }
QMenu { background: #152235; border: 1px solid #344d67; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #29435f; }
QMenu::item:disabled { color: #7b91a6; }
"""

from importlib.resources import files as _resource_files
STYLE += '\nQCheckBox::indicator:checked { image: url("'+str(_resource_files('jarvis.desktop').joinpath('assets','icons','check.svg'))+'"); }'

def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


def card(title, text):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(9)
    layout.addWidget(label(title, "eyebrow"))
    layout.addWidget(label(text))
    return frame


class Controller(QObject):
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
        self.ptt_hotkey_message="Maintenez ⌘⌥Espace, ou Espace lorsque le compagnon a le focus."
        self.ptt_enabled=False
        self.ptt_held=False
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
            self.voice_worker.cancel_task(candidates[0]['id'])
        else:
            self.voice_worker.cancel_task()

    def clear_tool_notice(self):
        self.tool_notice = ""
        self.changed.emit()

    def set_sounds(self, enabled):
        self.sounds_enabled = enabled
        if self.voice_worker:
            self.voice_worker.set_sounds(enabled)

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

    def set_push_to_talk(self,enabled):
        self.end_push_to_talk()
        self.ptt_enabled=bool(enabled)
        if self.voice_worker:self.voice_worker.set_push_to_talk(enabled)
        if enabled and self.voice_worker:
            self.microphone_muted=True;self.voice_worker.set_muted(True)
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
        if self.demo or not self.voice_worker or self.voice_state in {'starting','stopping','error'}:return
        self.voice_worker.run_routine(name)

    def mission_notice(self,mission,previous):
        status=mission.get('status')
        labels={'completed':'Votre mission est terminée','failed':'Une mission a échoué',
                'needs_confirmation':'Une mission attend votre accord vocal','needs_clarification':'Une mission attend une précision'}
        if status in labels and status!=previous:
            self.notice.emit({'key':f"mission:{mission['id']}:{status}",'text':labels[status], 'mission_id':mission['id']})

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

    def voice_finished(self, worker):
        if self.voice_worker is worker:
            self.voice_worker = None
            self.session_voice = None
            self.undo_tickets = []
            self.audio_levels.emit(0.0, 0.0)
            self.voice_mic_open = False
            self.input_suppressed = False
            if self.voice_state != "error":
                self.voice_state = "off"
            self.changed.emit()
        worker.deleteLater()
        if self.quit_after_voice:
            self.exit_ready.emit()

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
        self.voice_worker.announce(message)
        return True


class VoicePanel(QWidget):
    def __init__(self, controller, compact=False):
        super().__init__()
        self.controller = controller
        self.compact = compact
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addStretch(1)
        self.orb = Orb(220 if compact else 360)
        controller.audio_levels.connect(self.orb.set_levels)
        self.stage = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.stage.setSpacing(20 if not compact else 8)
        self.orb_slot = QWidget()
        orb_layout = QHBoxLayout(self.orb_slot) if compact else QVBoxLayout(self.orb_slot)
        orb_layout.setContentsMargins(0, 0, 0, 0)
        orb_layout.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)
        self.appearance_button = button('Apparence…', self.choose_appearance)
        self.appearance_button.setAccessibleName('Choisir une apparence de Jarvis')
        orb_layout.addWidget(self.appearance_button, 0, Qt.AlignmentFlag.AlignCenter)
        self.stage.addWidget(self.orb_slot, 1)
        self.mission = MissionDeck(controller, compact)
        self.stage.addWidget(self.mission, 1)
        layout.addLayout(self.stage)
        self.status = label("Votre assistant vocal", "greeting")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if compact:
            self.status.setStyleSheet("font-size: 21px;")
        layout.addWidget(self.status)
        self.hint = label("Parlez-moi simplement.", "intro")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setMinimumHeight(40)
        self.hint_area = QStackedWidget()
        self.hint_area.addWidget(self.hint)
        self.details_button = button('Voir les détails →', controller.details_requested.emit)
        self.details_button.setObjectName('quiet')
        self.hint_area.addWidget(self.details_button)
        layout.addWidget(self.hint_area)
        self.peek = label('', 'subtitle')
        self.peek.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.peek.setMaximumHeight(100)
        self.peek.setStyleSheet('background: rgba(36, 65, 86, 65); border: 1px solid #29465c; border-radius: 14px; padding: 10px; color: #bfdeed;')
        layout.addWidget(self.peek)
        layout.addStretch(2)
        self.controls = ControlDock(controller)
        controls = QHBoxLayout(self.controls)
        controls.setContentsMargins(8, 8, 8, 8)
        controls.setSpacing(8)
        self.voice_button = button("Démarrer Jarvis", self.toggle_voice, True)
        self.voice_button.setAccessibleName("Démarrer ou arrêter l’assistant vocal")
        controls.addWidget(self.voice_button)
        self.mic_button = button("Couper le micro", controller.toggle_microphone)
        controls.addWidget(self.mic_button)
        self.interrupt_button = button("Interrompre", controller.interrupt_voice)
        self.interrupt_button.setToolTip("Couper la réponse orale pour reprendre la parole. Les actions système déjà lancées peuvent continuer.")
        controls.addWidget(self.interrupt_button)
        layout.addWidget(self.controls)
        self.voice_notice = label("", "subtitle")
        self.voice_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.voice_notice)
        self.footnote = label("", "eyebrow")
        self.footnote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.footnote)
        controller.changed.connect(self.render)
        self.render()

    def toggle_voice(self):
        self.controller.stop_voice() if self.controller.voice_worker else self.controller.start_voice()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'footnote'):
            self.render()

    def choose_appearance(self):
        self.controller.appearance_requested.emit()

    def render(self):
        c = self.controller
        active = c.voice_worker is not None
        state = c.voice_state
        mission_shown = self.mission.render()
        beside = mission_shown and self.mission.expanded and not self.compact
        self.stage.setDirection(QBoxLayout.Direction.LeftToRight if beside else QBoxLayout.Direction.TopToBottom)
        self.mission.setMinimumWidth(300 if beside else 0)
        self.mission.setMaximumWidth(370 if beside else 16777215)
        has_details = bool(c.cards or c.task or c.activity)
        self.hint_area.setCurrentIndex(1 if has_details and state not in {"error", "starting"} else 0)
        self.details_button.setText(f'{len(c.cards)} carte(s) · Voir les détails →' if c.cards else
                                    'Suivre la tâche →' if c.task else 'Voir l’activité →')
        self.peek.setVisible(bool(c.cards) and not self.compact)
        if c.cards:
            latest = next(reversed(c.cards.values()))
            summary = latest['body'] if not latest['items'] else latest['items'][0]
            self.peek.setText(latest['title'] + '\n' + summary[:160])
        compact_orb = 140 if len(c.focus_missions()) > 1 else 180
        orb_size = (compact_orb if mission_shown else 220) if self.compact else (max(160, min(280, self.width()-340)) if beside else 280 if c.cards or mission_shown else 360)
        self.orb.setFixedSize(orb_size, orb_size)
        self.orb_slot.setMinimumHeight(orb_size + (0 if self.compact else self.appearance_button.sizeHint().height() + 12))
        self.orb.set_appearance(c.appearance)
        self.orb.dance = c.dance
        self.orb.state = c.avatar_state()
        self.orb.update()
        self.controls.active = active
        self.controls.refresh()
        self.orb.set_motion(not c.reduced_motion)
        if c.request_status and c.tool_timer.isActive() and state not in {"error","starting","stopping"} and c.audio_worker is None and not c.input_suppressed:
            self.hint_area.setCurrentIndex(0);self.hint.setText(c.request_status)
        states = {"off": "Votre assistant vocal", "starting": "Connexion en cours…",
                  "listening": "Je vous écoute", "thinking": "Je réfléchis…",
                  "speaking": "Jarvis vous répond", "muted": "Micro coupé",
                  "stopping": "À tout de suite…", "error": "Vocal indisponible"}
        self.status.setText(states.get(state, "Jarvis"))
        self.hint.setText("Cliquez sur Interrompre pour reprendre la parole." if state == "speaking" else
                          "Parlez naturellement, vos demandes restent vocales." if active else
                          "Une question, une idée, une action. Dites-le à Jarvis.")
        if c.input_suppressed and state == "listening":
            self.status.setText("Reprise de l’écoute…")
            self.hint.setText("Un instant, le temps que la sortie audio se termine.")
        if state == 'starting' and c.reconnecting:
            self.status.setText('Reconnexion en cours…')
            self.hint.setText('Une nouvelle conversation démarre, sans renvoyer vos demandes précédentes.')
        elif state == 'error' and c.can_reconnect:
            self.hint.setText('Reconnecter ouvre une nouvelle conversation. Vérifiez le résultat des actions précédentes dans Activité.')
        elif state == 'error':
            self.hint.setText('Vérifiez le message ci-dessous, puis réessayez ou ouvrez Réglages.')
        if c.tool_notice and not c.voice_error:
            self.hint.setText(c.tool_notice)
            self.hint.setStyleSheet("color: #bfe5f6; font-size: 12px; background: rgba(63, 106, 136, 35); border: 1px solid #284357; border-radius: 12px; padding: 5px;")
        else:
            self.hint.setStyleSheet("color: #94abc1; font-size: " + ("12px;" if self.compact else "14px;"))
        self.voice_button.setText('Fermeture…' if state == 'error' and active else
                                  'Arrêt en cours…' if state == 'stopping' else 'Arrêter' if active else
                                  'Reconnecter' if c.can_reconnect else 'Réessayer' if state == 'error' else 'Démarrer Jarvis')
        self.voice_button.setEnabled(not c.demo and c.audio_worker is None and state not in {"starting", "stopping"} and not (state == "error" and active))
        for control in (self.mic_button, self.interrupt_button):
            control.setVisible(active and not (control is self.mic_button and c.ptt_enabled))
            control.setEnabled(active and state not in {"starting", "stopping", "error"})
        self.mic_button.setText("Couper le micro" if c.voice_mic_open else "Réactiver le micro")
        if c.screen_operations and state not in {'off', 'error', 'stopping'}:
            self.status.setText('Observation d’écran en cours')
            self.hint_area.setCurrentIndex(0)
            self.hint.setText('Capture ou analyse ponctuelle demandée · aucun suivi continu de l’écran.')
        if c.audio_worker is not None:
            self.status.setText('Micro en test local' if c.local_mic_open else 'Test audio local' if c.audio_job_kind != 'scan' else 'Périphériques audio')
            self.hint_area.setCurrentIndex(0)
            if c.audio_job_kind == 'voice_preview':
                self.status.setText('Aperçu vocal · micro fermé')
            self.hint.setText('Arrêtez l’aperçu ou le test audio pour démarrer le vocal.')
        if c.local_mic_open:
            notice = 'Micro ouvert pour le test local · aucune voix envoyée à Gemini'
        elif c.audio_worker is not None:
            notice = 'Aperçu généré par Gemini · micro fermé' if c.audio_job_kind == 'voice_preview' else 'Opération audio locale en cours · Gemini déconnecté'
        elif c.voice_error:
            notice = c.voice_error
        elif c.demo:
            notice = "Démonstration visuelle · micro désactivé"
        elif c.input_suppressed:
            notice = "Écoute en pause pendant la sortie audio"
        elif c.voice_mic_open:
            notice = "Micro ouvert · voix envoyée à Gemini"
        elif active:
            notice = "Micro fermé"
        else:
            notice = "Le micro s’ouvre uniquement après votre activation."
        if c.ptt_enabled and active and not c.voice_error and state not in {'error','stopping'}:
            notice='Micro ouvert pendant le maintien' if c.ptt_held else 'Micro fermé · maintien pour parler activé'
            if state=='muted':
                self.status.setText('Maintenir pour parler')
                self.hint.setText(c.ptt_hotkey_message)
        self.voice_notice.setText(c.recovery_message or notice)
        self.voice_notice.setStyleSheet("color: #e5a0aa;" if c.voice_error else "color: #91a9c1;")
        self.footnote.setText("JARVIS · ASSISTANT VOCAL" if not active else "GEMINI LIVE · CONFIRMATIONS VOCALES")


class DesktopWindow(QMainWindow):
    def __init__(self, controller, shell, compact=False):
        super().__init__()
        self.shell = shell
        self.controller = controller
        self.compact = compact
        self.setWindowTitle("Jarvis · " + ("Compagnon" if compact else "Assistant vocal"))
        self.resize(460, 560) if compact else self.resize(1080, 800)
        self.setMinimumSize(440, 550) if compact else self.setMinimumSize(800, 730)
        if compact:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                                Qt.WindowType.WindowStaysOnTopHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setStyleSheet("QMainWindow { background: transparent; }")
        root = GlassSurface() if compact else QWidget()
        root.setObjectName("capsule" if compact else "shell")
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        if not compact:
            sidebar = QFrame()
            sidebar.setObjectName("sidebar")
            sidebar.setFixedWidth(195)
            nav = QVBoxLayout(sidebar)
            nav.setContentsMargins(18, 28, 18, 22)
            nav.addWidget(label("J A R V I S", "wordmark"))
            nav.addWidget(label("ASSISTANT VOCAL", "eyebrow"))
            nav.addSpacing(34)
            self.nav = []
            for i, text in enumerate(("Assistant", "Cartes", "Activité", "Réglages")):
                b = button(text, lambda checked=False, index=i: self.navigate(index))
                b.setObjectName("nav")
                b.setCheckable(True)
                self.nav.append(b)
                nav.addWidget(b)
            nav.addStretch()
            nav.addWidget(label("PENSÉ POUR LA VOIX", "eyebrow"))
            nav.addWidget(label("Parlez. Jarvis s’occupe de la suite.", "subtitle"))
            row.addWidget(sidebar)
        workspace = QVBoxLayout()
        workspace.setContentsMargins(28 if compact else 40, 26, 28 if compact else 40, 28)
        workspace.setSpacing(16)
        heading = QHBoxLayout()
        heading.addWidget(DragHandle("◌   J A R V I S") if compact else label("COMPAGNON VOCAL     /     JARVIS", "eyebrow"), 1)
        heading.addStretch()
        switch = button("Agrandir ↗" if compact else "Mode compact ↙", shell.switch_view)
        switch.setObjectName("quiet")
        heading.addWidget(switch)
        orb_mode = button('◉', shell.show_orb)
        orb_mode.setObjectName('quiet')
        orb_mode.setFixedSize(34, 34)
        orb_mode.setStyleSheet('padding: 0; font-size: 19px;')
        orb_mode.setToolTip('Mode orbe seul')
        orb_mode.setAccessibleName('Passer au mode orbe seul')
        heading.addWidget(orb_mode)
        if compact:
            close = button("×", self.close)
            close.setObjectName("quiet")
            close.setFixedSize(32, 32)
            close.setStyleSheet("padding: 0; font-size: 20px;")
            close.setAccessibleName("Fermer le compagnon")
            heading.addWidget(close)
        workspace.addLayout(heading)
        self.pages = QStackedWidget()
        self.assistant = VoicePanel(controller, compact)
        self.pages.addWidget(self.assistant)
        if not compact:
            self.cards_page = DetailPanel(controller)
            self.pages.addWidget(self.cards_page)
            self.activity = DetailPanel(controller, activity=True)
            self.pages.addWidget(self.activity)
            settings = QWidget()
            settings_layout = QVBoxLayout(settings)
            settings_layout.setContentsMargins(0, 0, 0, 0)
            settings_layout.addWidget(card("VOTRE VOIX, VOTRE COMMANDE",
                "Gemini Live écoute uniquement après activation. Les confirmations des outils restent vocales."))
            settings_layout.addWidget(card("ÉCOUTE ET RÉPONSE",
                "L’écoute est suspendue pendant la lecture de la voix de Jarvis pour éviter qu’il se réponde à lui-même. Cliquez sur Interrompre pour reprendre la parole."))
            settings_layout.addWidget(card("CONFIDENTIALITÉ",
                "Cette interface n’affiche et n’enregistre aucun texte de transcription. La session Gemini utilise le contexte de votre conversation ; les outils gardent leurs règles existantes de mémoire et de journalisation."))
            reduce = QCheckBox("Réduire les animations")
            reduce.setChecked(controller.reduced_motion)
            reduce.toggled.connect(self.set_reduced_motion)
            settings_layout.addWidget(reduce)
            sounds = QCheckBox("Sons discrets à l’activation et au changement du micro")
            sounds.setChecked(controller.sounds_enabled)
            sounds.toggled.connect(self.set_sounds)
            settings_layout.addWidget(sounds)
            settings_layout.addWidget(button("Jarvis au quotidien…", lambda: shell.experience.open()))
            settings_layout.addWidget(button("Palette de commandes · ⌘K", lambda: shell.experience.palette()))
            settings_layout.addWidget(button("Voix des avatars…", shell.show_voices))
            settings_layout.addWidget(button("Configurer les routines vocales…",shell.show_routines))
            settings_layout.addWidget(label('PÉRIPHÉRIQUES ET TESTS LOCAUX', 'eyebrow'))
            self.audio_settings = AudioSettings(controller)
            settings_layout.addWidget(self.audio_settings)
            self.hotkey_check = QCheckBox('Activer le raccourci global ⌘⇧Espace')
            self.hotkey_check.setChecked(controller.hotkey_enabled)
            self.hotkey_check.setEnabled(not controller.demo)
            self.hotkey_check.toggled.connect(shell.set_global_hotkey)
            settings_layout.addWidget(self.hotkey_check)
            self.hotkey_status = label(controller.hotkey_message, 'subtitle')
            settings_layout.addWidget(self.hotkey_status)
            self.hotkey_retry = button('Réessayer le raccourci', shell.retry_hotkey)
            settings_layout.addWidget(self.hotkey_retry)
            def render_hotkey():
                self.hotkey_status.setText(controller.hotkey_message)
                self.hotkey_retry.setEnabled(controller.hotkey_enabled and not controller.hotkey_active and not controller.demo)
            controller.changed.connect(render_hotkey)
            settings_layout.addStretch()
            settings_scroll = QScrollArea()
            settings_scroll.setWidgetResizable(True)
            settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            settings_scroll.setWidget(settings)
            self.pages.addWidget(settings_scroll)
            self.navigate(0)
        workspace.addWidget(self.pages, 1)
        row.addLayout(workspace, 1)
        self.shortcut = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
        self.shortcut.activated.connect(shell.show_compact)

    def navigate(self, index):
        self.shell.finish_transfer()
        self.pages.setCurrentIndex(index)
        for i, widget in enumerate(self.nav):
            widget.setChecked(index == i)

    def set_reduced_motion(self, checked):
        if checked:
            self.controller.dance.stop()
        self.controller.reduced_motion = checked
        self.shell.settings.setValue("appearance/reduced_motion", checked)
        self.controller.changed.emit()

    def set_sounds(self, checked):
        self.controller.set_sounds(checked)
        self.shell.settings.setValue("audio/sounds", checked)

    def closeEvent(self, event):
        if self.compact:
            self.shell.remember_companion()
        self.shell.finish_transfer()
        event.ignore()
        if self.shell.has_tray:
            self.hide()
        else:
            self.shell.quit()


class InsightRelay(QObject):
    """Carries insights from the monitor's worker thread to the GUI thread."""
    fired = Signal(object)


class DesktopShell:
    def __init__(self, app, controller, settings=None):
        self.app, self.controller = app, controller
        self.settings = settings if settings is not None else QSettings("Jarvis", "Desktop")
        controller.hotkey_enabled = self.settings.value('input/global_hotkey', True) in (True, 'true')
        for key, attribute in (('audio/input_device', 'input_choice'), ('audio/output_device', 'output_choice')):
            raw = self.settings.value(key)
            if raw is not None:
                try:
                    choice = json.loads(raw) if isinstance(raw, str) else raw
                    if choice is not None and not valid_choice(choice):
                        raise ValueError('Invalid device preference')
                    setattr(controller, attribute, choice)
                except (TypeError, ValueError):
                    controller.device_config_invalid = True
        controller.ptt_enabled=self.settings.value('input/push_to_talk',False) in (True,'true')
        controller.devices_changed.connect(self.save_devices)
        controller.sounds_enabled = self.settings.value("audio/sounds", False) in (True, "true")
        controller.reduced_motion = self.settings.value("appearance/reduced_motion", controller.reduced_motion) in (True, "true")
        from jarvis.desktop.appearances import AppearancePreference
        self.appearance_preference = AppearancePreference(self.settings)
        controller.appearance = self.appearance_preference.load()
        from jarvis.desktop.voices import VoicePreferences
        self.voice_preferences = VoicePreferences(self.settings)
        controller.selected_voice = self.voice_preferences.load(controller.appearance)
        self.voice_dialog = None
        controller.appearance_requested.connect(self.show_appearances)
        self.appearance_dialog = None
        self.routines_dialog = None
        self.position_restored = False
        self.orb_position_restored = False
        self.transfer = None
        controller.changed.connect(self.motion_changed)
        self.has_tray = QSystemTrayIcon.isSystemTrayAvailable()
        controller.exit_ready.connect(app.quit)
        self.full = DesktopWindow(controller, self)
        self.compact = CompanionWindow(controller, self)
        self.orb_window = OrbWindow(controller, self)
        controller.details_requested.connect(self.show_details)
        controller.mission_details_requested.connect(self.show_mission_details)
        self.tray = None
        self.tray_controls = None
        if self.has_tray:
            self.tray = QSystemTrayIcon(app)
            self.tray_controls = TrayControls(self, self.tray)
            self.tray.show()
        app.setQuitOnLastWindowClosed(False)
        self.hotkey = GlobalHotkey(self.show_compact, parent=controller,
                                   demo=controller.demo or app.platformName() == 'offscreen')
        self.hotkey.changed.connect(self.hotkey_changed)
        self.hotkey.set_enabled(controller.hotkey_enabled)
        app.aboutToQuit.connect(self.hotkey.close)
        from jarvis.desktop.hotkey import HoldHotkey
        self.hold_hotkey=HoldHotkey(controller.begin_push_to_talk,controller.end_push_to_talk,parent=controller,
                                   demo=controller.demo or app.platformName()=='offscreen')
        self.hold_hotkey.changed.connect(self.hold_hotkey_changed)
        self.hold_hotkey.set_enabled(controller.ptt_enabled)
        app.aboutToQuit.connect(self.hold_hotkey.close)
        from jarvis.desktop.recovery import VoiceRecovery,MacPowerMonitor
        self.recovery=VoiceRecovery(controller,self.settings.value('voice/auto_reconnect',app.platformName()!='offscreen') in (True,'true'))
        controller.recovery=self.recovery
        self.power=MacPowerMonitor(controller)
        self.power.sleeping.connect(self.recovery.before_sleep)
        self.power.waking.connect(self.recovery.after_wake)
        if not controller.demo:self.power.start()
        app.aboutToQuit.connect(self.power.close)
        app.aboutToQuit.connect(self.recovery.close)
        self.quit_guard = QuitGuard(self, app)
        app.installEventFilter(self.quit_guard)
        self.onboarding = None
        self.usage_window = None
        self.metrics_window = None
        self.insights_enabled = self.settings.value('insights/enabled', True) in (True, 'true')
        self.insights_spoken = self.settings.value('insights/voice', True) in (True, 'true')
        self._start_metrics_sampler()
        self._start_insight_monitor()
        from jarvis.desktop.experience import Experience
        self.experience = Experience(self)
        controller.experience = self.experience
        self.maybe_show_onboarding()
        if not controller.demo and app.platformName() != "offscreen" and self.settings.value("experience/setup_seen", False) not in (True,"true"):
            if self.onboarding:self.onboarding.finished.connect(lambda: self.experience.setup())
            else:self.experience.setup()

    def _start_metrics_sampler(self):
        """Accrue machine-metrics history while Jarvis runs (real desktop only)."""
        self.metrics_sampler = None
        self.metrics_timer = None
        if self.controller.demo or self.app.platformName() == "offscreen":
            return
        from jarvis.metrics.sampler import MetricsSampler

        sampler = MetricsSampler()
        if not sampler.available():
            return
        self.metrics_sampler = sampler
        sampler.tick()  # one baseline reading immediately
        timer = QTimer(self.full)
        timer.setInterval(20_000)
        timer.timeout.connect(sampler.tick)
        timer.start()
        self.metrics_timer = timer
        self.app.aboutToQuit.connect(timer.stop)

    def _start_insight_monitor(self):
        """Proactive anomaly alerts, checked off the GUI thread every 5 minutes.

        Rides on the sampler's history, so it only runs where the sampler does.
        """
        self.insight_monitor = None
        self.insight_timer = None
        if self.metrics_sampler is None:
            return
        from jarvis.insights.detector import InsightDetector, InsightMonitor
        from jarvis.usage.store import UsageStore

        self.insight_relay = InsightRelay()
        self.insight_relay.fired.connect(self.show_insight)
        detector = InsightDetector(metrics=self.metrics_sampler.store, usage=UsageStore(),
                                   probe=self.metrics_sampler.probe)
        self.insight_monitor = InsightMonitor(detector, notifier=self.insight_relay.fired.emit)
        timer = QTimer(self.full)
        timer.setInterval(5 * 60_000)
        timer.timeout.connect(self.check_insights)
        timer.start()
        self.insight_timer = timer
        self.app.aboutToQuit.connect(timer.stop)

    def check_insights(self):
        if self.insight_monitor is None or not self.insights_enabled:
            return
        threading.Thread(target=self.insight_monitor.tick, name='jarvis-insights',
                         daemon=True).start()

    def set_insights_enabled(self, enabled):
        self.insights_enabled = bool(enabled)
        self.settings.setValue('insights/enabled', self.insights_enabled)

    def set_insights_spoken(self, enabled):
        self.insights_spoken = bool(enabled)
        self.settings.setValue('insights/voice', self.insights_spoken)

    def show_insight(self, insight):
        if not self.insights_enabled:
            return
        if self.insights_spoken:
            self.controller.announce(insight.message)
        if self.tray is not None:
            icon = (QSystemTrayIcon.MessageIcon.Warning if insight.severity == 'warning'
                    else QSystemTrayIcon.MessageIcon.Information)
            self.tray.showMessage(f'Jarvis · {insight.title}', insight.message, icon, 10_000)
        else:
            from jarvis.schedule.runner import macos_notifier
            macos_notifier(f'{insight.title} : {insight.message}')

    def show_usage(self):
        """Open the token-usage dashboard (its data loads asynchronously)."""
        from jarvis.desktop.charts import UsageWindow

        if self.usage_window is None:
            self.usage_window = UsageWindow()
        else:
            self.usage_window.reload()
        self.usage_window.show()
        self.usage_window.raise_()
        self.usage_window.activateWindow()

    def show_metrics(self):
        """Open the machine-activity dashboard (data loads asynchronously)."""
        from jarvis.desktop.charts import MetricsWindow

        if self.metrics_window is None:
            self.metrics_window = MetricsWindow()
        else:
            self.metrics_window.reload()
        self.metrics_window.show()
        self.metrics_window.raise_()
        self.metrics_window.activateWindow()

    def maybe_show_onboarding(self):
        """Show the first-run permission screen once, on a real desktop only."""
        from jarvis.desktop import onboarding

        if self.controller.demo or self.app.platformName() == "offscreen":
            return None
        if not onboarding.needs_onboarding(self.settings):
            return None
        self.onboarding = onboarding.make_onboarding_dialog(self.settings)
        self.onboarding.show()
        self.onboarding.raise_()
        return self.onboarding

    def save_devices(self):
        self.settings.setValue('audio/input_device', json.dumps(self.controller.input_choice))
        self.settings.setValue('audio/output_device', json.dumps(self.controller.output_choice))

    def hold_hotkey_changed(self):
        self.controller.ptt_hotkey_message=self.hold_hotkey.message
        self.controller.changed.emit()

    def set_auto_reconnect(self,enabled):
        self.settings.setValue('voice/auto_reconnect',enabled)
        self.recovery.set_enabled(enabled)

    def set_push_to_talk(self,enabled):
        self.controller.set_push_to_talk(enabled)
        self.settings.setValue('input/push_to_talk',enabled)
        self.hold_hotkey.set_enabled(enabled)

    def set_global_hotkey(self, enabled):
        self.controller.hotkey_enabled = enabled
        self.settings.setValue('input/global_hotkey', enabled)
        self.hotkey.set_enabled(enabled)

    def retry_hotkey(self):
        self.hotkey.set_enabled(self.controller.hotkey_enabled)

    def hotkey_changed(self):
        self.controller.hotkey_active = self.hotkey.active
        self.controller.hotkey_message = self.hotkey.message
        for window in (self.full, self.compact, self.orb_window):
            window.shortcut.setEnabled(not self.hotkey.active)
        self.controller.changed.emit()

    def set_appearance(self, appearance):
        self.controller.dance.stop()
        self.controller.appearance = self.appearance_preference.save(appearance)
        self.controller.selected_voice = self.voice_preferences.load(self.controller.appearance)
        self.controller.appearance_changed.emit(self.controller.appearance)
        self.controller.changed.emit()

    def show_routines(self):
        from jarvis.desktop.routines import RoutineDialog
        if self.routines_dialog is not None:
            self.routines_dialog.close();self.routines_dialog.deleteLater()
        self.routines_dialog=RoutineDialog(self.controller,self.visible_window())
        self.routines_dialog.show()

    def set_avatar_voice(self, appearance, voice):
        self.voice_preferences.save(appearance, voice)
        if appearance == self.controller.appearance:
            self.controller.selected_voice = voice
        self.controller.changed.emit()

    def show_voices(self):
        from jarvis.desktop.voice_selector import VoiceSelector
        if self.voice_dialog is not None:
            self.voice_dialog.close()
            self.voice_dialog.deleteLater()
        self.voice_dialog = VoiceSelector(self, self.visible_window())
        self.voice_dialog.show()

    def show_appearances(self):
        from jarvis.desktop.avatar_selector import AvatarSelector
        if self.appearance_dialog is not None:
            self.appearance_dialog.close()
            self.appearance_dialog.deleteLater()
        self.appearance_dialog = AvatarSelector(self.controller.appearance, self.visible_window())
        self.appearance_dialog.chosen.connect(self.set_appearance)
        self.appearance_dialog.show()

    def show_settings(self):
        self.show_full()
        self.finish_transfer()
        self.full.navigate(3)

    def hide_windows(self):
        # Never strand a running assistant without a way to reopen it.
        if not self.has_tray:
            return
        self.finish_transfer()
        self.remember_companion()
        self.remember_orb()
        for window in (self.full, self.compact, self.orb_window):
            window.hide()

    def restore_companion(self):
        if self.position_restored:
            return
        self.position_restored = True
        self.restore_position(self.compact, 'companion/position')

    def restore_position(self, window, key):
        point = self.settings.value(key)
        screens = QGuiApplication.screens()
        screen = next((s for s in screens if isinstance(point, QPoint) and
                       s.availableGeometry().contains(point)), QGuiApplication.primaryScreen())
        if screen is None:
            return
        area = screen.availableGeometry()
        if not isinstance(point, QPoint):
            point = QPoint(area.right() - window.width() - 24,
                           area.bottom() - window.height() - 24)
        x = max(area.left(), min(point.x(), area.right() - window.width() + 1))
        y = max(area.top(), min(point.y(), area.bottom() - window.height() + 1))
        window.move(x, y)

    def remember_companion(self):
        if self.position_restored and not self.controller.demo:
            origin = getattr(self.compact, "dance_origin", None)
            self.settings.setValue("companion/position", origin if origin is not None else self.compact.pos())

    def remember_orb(self):
        if self.orb_position_restored and not self.controller.demo:
            self.settings.setValue('orb/position', self.orb_window.pos())

    def visible_window(self):
        return next((w for w in (self.full, self.compact, self.orb_window) if w.isVisible()), self.full)

    def show_orb(self):
        if not self.orb_position_restored:
            self.orb_position_restored = True
            self.restore_position(self.orb_window, 'orb/position')
        self.present(self.orb_window, self.visible_window())

    def show_details(self):
        self.show_full()
        self.finish_transfer()
        self.full.navigate(1 if self.controller.cards else 2)

    def show_mission_details(self):
        self.show_full()
        self.finish_transfer()
        self.full.navigate(2)

    def finish_transfer(self):
        if self.transfer is not None:
            self.transfer.complete()

    def motion_changed(self):
        if self.controller.reduced_motion:
            self.finish_transfer()

    def present(self, target, source):
        self.finish_transfer()
        animate = source.assistant.orb.isVisible() and not target.isVisible() and not self.controller.reduced_motion
        pixmap = source.assistant.orb.grab() if animate else None
        start = QRect(source.assistant.orb.mapToGlobal(QPoint()), source.assistant.orb.size())
        if source is self.compact:
            self.remember_companion()
        if source is self.orb_window:
            self.remember_orb()
        target.show()
        for window in (self.full, self.compact, self.orb_window):
            if window is not target:
                window.hide()
        target.raise_()
        target.activateWindow()
        # Keep command controls discoverable, with no forced focus on an action.
        if animate:
            orb = target.assistant.orb
            end = QRect(orb.mapToGlobal(QPoint()), orb.size())
            effect = QGraphicsOpacityEffect(orb)
            effect.setOpacity(0.0)
            orb.setGraphicsEffect(effect)
            def finished():
                orb.setGraphicsEffect(None)
                self.transfer = None
            self.transfer = OrbTransfer(pixmap, start, end, finished)
            self.transfer.begin()

    def show_full(self):
        if self.compact.isVisible() or self.orb_window.isVisible():
            self.full.navigate(0)
        self.present(self.full, self.visible_window())

    def show_compact(self):
        self.restore_companion()
        self.present(self.compact, self.visible_window())

    def switch_view(self):
        self.show_full() if self.compact.isVisible() else self.show_compact()

    def quit(self):
        self.finish_transfer()
        self.remember_companion()
        self.remember_orb()
        if self.controller.audio_worker:
            self.controller.quit_after_voice = True
            self.controller.stop_audio_job()
        elif self.controller.voice_worker:
            self.controller.quit_after_voice = True
            self.controller.stop_voice()
        else:
            self.app.quit()


class QuitGuard(QObject):
    def __init__(self, shell, parent):
        super().__init__(parent)
        self.shell = shell

    def eventFilter(self, watched, event):
        c = self.shell.controller
        if event.type() == QEvent.Type.Quit and (c.voice_worker or c.audio_worker):
            self.shell.quit()
            return True
        return False


def run(demo=False, compact=False, orb=False):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Jarvis")
    app.setOrganizationName("Jarvis")
    app.setStyleSheet(STYLE)
    controller = Controller(demo=demo)
    shell = DesktopShell(app, controller)
    shell.show_orb() if orb else shell.show_compact() if compact else shell.show_full()
    # Qt catches Python exceptions raised inside paint/timer callbacks. The
    # default SIGINT handler therefore prints KeyboardInterrupt instead of
    # reliably ending app.exec(). Queue a normal quit through the event loop.
    interrupt_requested = False
    draining_interrupt = False

    def request_interrupt(signum, frame):
        nonlocal interrupt_requested
        interrupt_requested = True  # No Qt calls inside a Python signal handler.

    def drain_interrupt():
        nonlocal interrupt_requested, draining_interrupt
        if not interrupt_requested or draining_interrupt:
            return
        interrupt_requested = False
        draining_interrupt = True
        try:
            shell.quit()  # Retain the existing guard against killing a worker.
        finally:
            draining_interrupt = False

    previous_sigint = signal.signal(signal.SIGINT, request_interrupt)
    signal_pump = QTimer(app)
    signal_pump.setInterval(100)
    signal_pump.timeout.connect(drain_interrupt)
    signal_pump.start()
    try:
        return app.exec()
    finally:
        signal_pump.stop()
        signal_pump.deleteLater()
        signal.signal(signal.SIGINT, previous_sigint)

