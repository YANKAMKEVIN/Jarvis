"""Glanceable mission state beside the assistant, using its shared controller."""
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from jarvis.desktop.presentation import MISSION_GUIDANCE, STATUS_TEXT, TASK_TEXT

EXPANDED_STATES = {'running', 'cancelling', 'needs_confirmation', 'needs_clarification'}


def caption(name=None):
    label = QLabel()
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


class MissionPanel(QFrame):
    def __init__(self, controller, compact=False):
        super().__init__()
        self.controller, self.compact = controller, compact
        self.identity = None
        self.expanded = False
        self.setObjectName('missionPanel')
        self.setAccessibleName('Suivi de la mission en cours')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        self.heading = caption('eyebrow')
        self.objective = caption()
        self.objective.setStyleSheet('font-size: 18px; font-weight: 500;')
        self.state = caption()
        self.current = caption()
        self.steps = [caption('subtitle') for _ in range(3)]
        self.guidance = caption('subtitle')
        for widget in (self.heading, self.objective, self.state, self.current, *self.steps, self.guidance):
            layout.addWidget(widget)
        self.summary = QPushButton()
        self.summary.setObjectName('missionSummary')
        self.summary.clicked.connect(controller.mission_details_requested.emit)
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.details = QPushButton('Détails →')
        self.details.clicked.connect(controller.mission_details_requested.emit)
        self.cancel = QPushButton('Annuler la mission')
        self.cancel.setToolTip('Demander l’arrêt de la mission. Une action déjà lancée peut se terminer.')
        self.cancel.clicked.connect(controller.cancel_task)
        self.dismiss = QPushButton('Masquer')
        self.dismiss.clicked.connect(self.dismiss_bilan)
        for widget in (self.details, self.cancel, self.dismiss):
            buttons.addWidget(widget)
        self.buttons = buttons
        layout.addLayout(buttons)
        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.fade = QPropertyAnimation(self.opacity, b'opacity', self)
        self.fade.setDuration(220)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setVisible(False)

    def dismiss_bilan(self):
        task = self.controller.task
        if task and task['status'] not in EXPANDED_STATES:
            self.controller.hidden_mission_bilan = task['id']
            self.controller.changed.emit()

    def render(self):
        c, task = self.controller, self.controller.task
        shown = bool(task and task['id'] != c.hidden_mission_bilan)
        if not shown:
            self.fade.stop()
            self.opacity.setOpacity(1)
            self.identity = None
            self.expanded = False
            self.hide()
            return False
        status = task['status']
        self.expanded = status in EXPANDED_STATES
        objective = ' '.join((task.get('objective') or 'Votre mission').split())
        state = TASK_TEXT.get(status, TASK_TEXT['unknown'])
        color = ('#ee99b9' if status in {'failed', 'unknown', 'budget_exceeded'} else
                 '#c5adff' if c.voice_state in {'thinking', 'speaking'} else '#87d2ff')
        self.setStyleSheet('QFrame#missionPanel { background: rgba(22, 40, 57, 195); border: 1px solid #2b455c; '
                          'border-left: 2px solid ' + color + '; border-radius: 14px; } '
                          'QPushButton#missionSummary { text-align: left; background: transparent; border: 0; padding: 0; }')
        self.heading.setText('MISSION EN COURS' if status in {'running', 'cancelling'} else 'VOTRE ACCORD VOCAL' if status == 'needs_confirmation' else 'PRÉCISION DEMANDÉE')
        available = max(150, self.width()-36)
        self.objective.setText(self.objective.fontMetrics().elidedText(objective, Qt.TextElideMode.ElideRight, int(available * (1.7 if self.expanded else 1))))
        self.objective.setToolTip(objective)
        self.state.setText(state)
        current = task.get('current', '')
        self.current.setText('En cours · ' + current if current else 'Jarvis prépare la suite…' if status == 'running' else '')
        last_steps = task['steps'][-3:]
        for index, widget in enumerate(self.steps):
            widget.setText((last_steps[index]['label'] + ' · ' + STATUS_TEXT.get(last_steps[index]['status'], 'Résultat reçu')) if index < len(last_steps) else '')
            widget.setVisible(not self.compact and self.expanded and index < len(last_steps))
        self.guidance.setText(MISSION_GUIDANCE.get(status, MISSION_GUIDANCE['unknown']))
        for widget in (self.heading, self.current, self.guidance):
            widget.setVisible(not self.compact and self.expanded and bool(widget.text()))
        self.objective.setVisible(not self.compact)
        self.state.setVisible(not self.compact)
        self.summary.setVisible(self.compact)
        short = self.fontMetrics().elidedText(objective, Qt.TextElideMode.ElideRight, max(150, self.width()-36))
        stage = ('En cours · ' + current) if current and status == 'running' else state
        stage = self.fontMetrics().elidedText(stage, Qt.TextElideMode.ElideRight, max(150, self.width()-36))
        self.summary.setText(short + '\n' + stage)
        self.summary.setToolTip(objective + '\n' + state + '\nOuvrir les détails de la mission')
        self.summary.setAccessibleName('Mission : ' + objective + '. ' + state + '. Ouvrir les détails.')
        self.details.setVisible(not self.compact)
        self.cancel.setVisible(not self.compact and status in {'running', 'cancelling'})
        self.cancel.setText('Annulation demandée…' if status == 'cancelling' else 'Annuler la mission')
        self.cancel.setEnabled(status == 'running' and c.voice_worker is not None and c.voice_state not in {'starting', 'stopping', 'error'} and not c.demo)
        self.dismiss.setVisible(not self.compact and not self.expanded)
        identity = (task['id'], self.expanded)
        self.show()
        if c.reduced_motion or not self.isVisible():
            self.fade.stop()
            self.opacity.setOpacity(1)
        elif identity != self.identity:
            self.fade.stop()
            self.fade.setStartValue(0.0)
            self.fade.setEndValue(1.0)
            self.fade.start()
        self.identity = identity
        return True

    def hideEvent(self, event):
        self.fade.stop()
        self.opacity.setOpacity(1)
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'fade'):
            self.render()
