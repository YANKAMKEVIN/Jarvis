"""VoicePanel: the orb, status, suggestions and error panel of the voice view."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.desktop.app_widgets import PeekCard, button, label
from jarvis.desktop.mission_panel import MissionDeck
from jarvis.desktop.presentation import count_label, shorten
from jarvis.desktop.surfaces import ControlDock
from jarvis.desktop.visuals import Orb, state_tint


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
        # The title takes a hint of the orb's state colour and fades in when it changes.
        self.status_tint = self.status_shown = None
        self.status_opacity = QGraphicsOpacityEffect(self.status)
        self.status.setGraphicsEffect(self.status_opacity)
        self.status_fade = QPropertyAnimation(self.status_opacity, b'opacity', self)
        self.status_fade.setDuration(240)
        self.status_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
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
        self.suggestions = label('', 'subtitle')
        self.suggestions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.suggestions.setAccessibleName('Exemples de demandes à dire')
        self.suggestions.hide()
        layout.addWidget(self.suggestions)
        self.suggestion_tick = 0
        self.permission_snapshot = None
        self.suggestion_timer = QTimer(self)
        self.suggestion_timer.setInterval(7000)
        self.suggestion_timer.timeout.connect(self.next_suggestions)
        self.error_banner = QFrame()
        self.error_banner.setObjectName('errorBanner')
        self.error_banner.setAccessibleName('Problème vocal')
        banner = QHBoxLayout(self.error_banner)
        banner.setContentsMargins(14, 10, 10, 10)
        banner.setSpacing(12)
        icon = label('!', 'errorIcon')
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(22, 22)
        banner.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.error_text = label('', 'errorText')
        banner.addWidget(self.error_text, 1)
        self.error_action = button('Réessayer', self.resolve_error)
        self.error_kind = 'retry'
        banner.addWidget(self.error_action, 0, Qt.AlignmentFlag.AlignVCenter)
        self.error_banner.hide()
        layout.addWidget(self.error_banner)
        self.peek = PeekCard()
        self.peek.clicked.connect(controller.details_requested.emit)
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
        self.mic_button.setToolTip("Couper ou réactiver le micro · touche M")
        controls.addWidget(self.mic_button)
        self.interrupt_button = button("Interrompre · Échap", controller.interrupt_voice)
        self.interrupt_button.setAccessibleName("Interrompre la réponse")
        self.interrupt_button.setToolTip("Couper la réponse orale pour reprendre la parole (touche Échap). Les actions système déjà lancées peuvent continuer.")
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

    def fit_orb(self, wanted):
        """Largest orb up to `wanted` that leaves room for what is shown under it."""
        spacing = self.layout().spacing()
        used = self.appearance_button.sizeHint().height() + 12 + 2 * spacing
        for widget in (self.status, self.hint_area, self.suggestions, self.error_banner, self.peek,
                       self.controls, self.voice_notice, self.footnote):
            if not widget.isHidden():
                height = widget.heightForWidth(self.width()) if widget.hasHeightForWidth() else -1
                used += (height if height > 0 else widget.sizeHint().height()) + spacing
        if self.mission.isVisibleTo(self):
            used += self.mission.sizeHint().height() + self.stage.spacing()
        return max(160, min(wanted, self.height() - used))

    def next_suggestions(self):
        self.suggestion_tick += 1
        self.render_suggestions()

    def permissions(self):
        """macOS permission statuses, read once; never queried in the demo or offscreen."""
        if self.permission_snapshot is None:
            self.permission_snapshot = {}
            if not self.controller.demo and QApplication.platformName() != 'offscreen':
                from jarvis.desktop.onboarding import default_snapshot
                self.permission_snapshot = default_snapshot()
        return self.permission_snapshot

    def render_suggestions(self, shown=None):
        from jarvis.desktop.presentation import suggestions
        if shown is not None:
            self.suggestions.setVisible(shown)
        shown = not self.suggestions.isHidden()
        if shown:
            self.suggestions.setText('Essayez :  ' + '   ·   '.join(
                '« ' + phrase + ' »' for phrase in suggestions(self.permissions(), self.suggestion_tick)))
        rotating = shown and self.isVisible() and not self.controller.reduced_motion
        if rotating != self.suggestion_timer.isActive():
            self.suggestion_timer.start() if rotating else self.suggestion_timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.render_suggestions()

    def hideEvent(self, event):
        self.suggestion_timer.stop()
        super().hideEvent(event)

    def resolve_error(self):
        """Banner button: go where the error can be fixed, or start the voice again."""
        shell = getattr(self.window(), 'shell', None)
        if self.error_kind == 'api_key' and shell is not None:
            shell.experience.setup()
        elif self.error_kind == 'settings' and shell is not None:
            shell.show_settings()
        elif self.controller.voice_worker is None:
            self.controller.start_voice()

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
        self.details_button.setText(count_label(len(c.cards), 'carte') + ' · Voir les détails →' if c.cards else
                                    'Suivre la tâche →' if c.task else 'Voir l’activité →')
        self.peek.setVisible(bool(c.cards) and not self.compact)
        if c.cards:
            latest = next(reversed(c.cards.values()))
            summary = latest['body'] if not latest['items'] else latest['items'][0]
            self.peek.show_card(latest['title'], shorten(summary))
        self.orb.set_appearance(c.appearance)
        self.orb.dance = c.dance
        self.orb.state = c.avatar_state()
        self.orb.backchannel_enabled = c.backchannel
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
        if c.wake_standby and state == "muted":
            self.status.setText("En veille")
        self.hint.setText("Appuyez sur Échap ou cliquez sur Interrompre pour reprendre la parole." if state == "speaking" else
                          "Parlez naturellement, vos demandes restent vocales." if active else
                          "Une question, une idée, une action. Dites-le à Jarvis.")
        if c.wake_standby and state == "muted":
            self.hint.setText("Dites « Jarvis » pour parler.")
        if c.input_suppressed and state == "listening":
            self.status.setText("Reprise de l’écoute…")
            self.hint.setText("Un instant, le temps que la sortie audio se termine.")
        if state == 'starting' and c.reconnecting:
            self.status.setText('Reconnexion en cours…')
            self.hint.setText('Une nouvelle conversation démarre, sans renvoyer vos demandes précédentes.')
        elif state == 'error' and c.can_reconnect:
            self.hint.setText('Reconnecter ouvre une nouvelle conversation. Vérifiez le résultat des actions précédentes dans Activité.')
        elif state == 'error':
            self.hint.setText('Le vocal n’a pas pu démarrer. La cause et la marche à suivre sont indiquées ci-dessous.')
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
        self.mic_button.setText(("Couper le micro" if c.voice_mic_open else "Réactiver le micro") + " · M")
        self.mic_button.setAccessibleName("Couper le micro" if c.voice_mic_open else "Réactiver le micro")
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
        elif c.wake_standby:
            notice = "Veille locale · rien n’est envoyé à Gemini avant « Jarvis »"
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
        # Examples to say only fill an otherwise empty, idle or listening screen.
        self.render_suggestions(
            not self.compact and state in {'off', 'listening'} and not c.voice_error and not mission_shown
            and not c.cards and not has_details and c.audio_worker is None and not c.input_suppressed
            and not c.screen_operations and not (c.tool_notice or c.request_status)
            and not (c.ptt_enabled and active))
        # A voice error gets its own banner with the fitting next step; the line
        # under the dock then only carries the reconnection countdown, if any.
        self.error_banner.setVisible(bool(c.voice_error))
        if c.voice_error:
            from jarvis.desktop.recovery import voice_error_action
            self.error_kind, action = voice_error_action(c.voice_error, c.can_reconnect)
            self.error_text.setText(c.voice_error)
            self.error_action.setText(action)
            self.error_action.setEnabled(self.error_kind != 'retry' or self.voice_button.isEnabled())
        self.voice_notice.setText(c.recovery_message if c.voice_error else c.recovery_message or notice)
        self.voice_notice.setStyleSheet("color: #e5a0aa;" if c.voice_error else "color: #91a9c1;")
        # The footer is reserved for the state of the connection.
        self.footnote.setText("DÉMONSTRATION · HORS LIGNE" if c.demo else
                              "GEMINI LIVE · RECONNEXION…" if state == "starting" and c.reconnecting else
                              "GEMINI LIVE · CONNEXION…" if state == "starting" else
                              "GEMINI LIVE · DÉCONNEXION…" if state == "stopping" else
                              "GEMINI LIVE · CONNEXION INTERROMPUE" if state == "error" else
                              "GEMINI LIVE · CONNECTÉ · CONFIRMATIONS VOCALES" if active else
                              "GEMINI LIVE · HORS LIGNE")
        compact_orb = 140 if len(c.focus_missions()) > 1 else 180
        orb_size = (compact_orb if mission_shown else 220) if self.compact else (max(160, min(280, self.width()-340)) if beside else self.fit_orb(280 if c.cards or mission_shown or c.voice_error else 360))
        self.orb.setFixedSize(orb_size, orb_size)
        self.orb_slot.setMinimumHeight(orb_size + (0 if self.compact else self.appearance_button.sizeHint().height() + 12))
        tint = state_tint(self.orb.state)
        if tint != self.status_tint:
            self.status_tint = tint
            self.status.setStyleSheet(f"color: {tint};" + (" font-size: 21px;" if self.compact else ""))
        shown = (self.status.text(), tint)
        if shown != self.status_shown:
            self.status_fade.stop()
            if self.status_shown is None or c.reduced_motion or not self.status.isVisible():
                self.status_opacity.setOpacity(1.0)
            else:
                self.status_fade.setStartValue(0.25)
                self.status_fade.setEndValue(1.0)
                self.status_fade.start()
            self.status_shown = shown
        elif c.reduced_motion and self.status_fade.state() == QPropertyAnimation.State.Running:
            self.status_fade.stop()
            self.status_opacity.setOpacity(1.0)
