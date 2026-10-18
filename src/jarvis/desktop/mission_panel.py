"""Glanceable mission state beside the assistant, using its shared controller."""
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from jarvis.desktop.presentation import MISSION_GUIDANCE, STATUS_TEXT, TASK_TEXT

EXPANDED_STATES = {'queued', 'running', 'cancelling', 'needs_confirmation', 'needs_clarification'}


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
        self.bound_task = None
        self.dense = False
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
        self.summary.clicked.connect(self.open_details)
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.details = QPushButton('Détails →')
        self.details.clicked.connect(self.open_details)
        self.cancel = QPushButton('Annuler la mission')
        self.cancel.setToolTip('Demander l’arrêt de la mission. Une action déjà lancée peut se terminer.')
        self.pressed_task_id = None
        self.cancel.pressed.connect(self.capture_cancel_target)
        self.cancel.clicked.connect(lambda: controller.cancel_task(self.pressed_task_id) if self.pressed_task_id else None)
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
        task = self.bound_task
        if task and task['status'] not in EXPANDED_STATES:
            self.controller.hidden_mission_bilan = task['id']
            self.controller.changed.emit()

    def capture_cancel_target(self):
        self.pressed_task_id = self.bound_task['id'] if self.bound_task else None

    def open_details(self):
        if self.bound_task:
            self.controller.select_mission(self.bound_task['id'])
        self.controller.mission_details_requested.emit()

    def render(self, task=None, dense=False):
        c = self.controller
        task = task if task is not None else c.task
        self.bound_task, self.dense = task, dense
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
        self.heading.setText('EN ATTENTE' if status == 'queued' else 'MISSION EN COURS' if status in {'queued', 'running', 'cancelling'} else 'VOTRE ACCORD VOCAL' if status == 'needs_confirmation' else 'PRÉCISION DEMANDÉE')
        available = max(150, self.width()-36)
        self.objective.setText(self.objective.fontMetrics().elidedText(objective, Qt.TextElideMode.ElideRight, int(available * (1.7 if self.expanded and not dense else 1))))
        self.objective.setToolTip(objective)
        self.state.setText(state)
        current = task.get('current', '')
        self.current.setText('En cours · ' + current if current else 'Jarvis prépare la suite…' if status == 'running' else '')
        last_steps = task['steps'][-1 if dense else -3:]
        for index, widget in enumerate(self.steps):
            widget.setText((last_steps[index]['label'] + ' · ' + STATUS_TEXT.get(last_steps[index]['status'], 'Résultat reçu')) if index < len(last_steps) else '')
            widget.setVisible(not self.compact and self.expanded and index < len(last_steps))
        self.guidance.setText(MISSION_GUIDANCE.get(status, MISSION_GUIDANCE['unknown']))
        for widget in (self.heading, self.current, self.guidance):
            widget.setVisible(not self.compact and not dense and self.expanded and bool(widget.text()))
        self.objective.setVisible(not self.compact)
        self.state.setVisible(not self.compact)
        self.summary.setVisible(self.compact)
        short = self.fontMetrics().elidedText(objective, Qt.TextElideMode.ElideRight, max(150, self.width()-36))
        stage = ('En cours · ' + current) if current and status == 'running' else state
        stage = self.fontMetrics().elidedText(stage, Qt.TextElideMode.ElideRight, max(150, self.width()-36))
        if dense:
            self.state.setText(stage)
        self.summary.setText(short + '\n' + stage)
        self.summary.setToolTip(objective + '\n' + state + '\nOuvrir les détails de la mission')
        self.summary.setAccessibleName('Mission : ' + objective + '. ' + state + '. Ouvrir les détails.')
        self.details.setVisible(not self.compact)
        self.cancel.setVisible(not self.compact and status in {'queued', 'running', 'cancelling'})
        self.cancel.setText('Annulation demandée…' if status == 'cancelling' else 'Annuler' if dense else 'Annuler la mission')
        self.cancel.setAccessibleName('Annuler la mission : ' + objective)
        self.cancel.setEnabled(status in {'queued', 'running'} and c.voice_worker is not None and c.voice_state not in {'starting', 'stopping', 'error'} and not c.demo)
        self.dismiss.setVisible(not self.compact and not self.expanded)
        self.layout().setContentsMargins(12 if dense else 16, 10 if dense else 14, 12 if dense else 16, 10 if dense else 14)
        self.layout().setSpacing(5 if dense else 9)
        self.cancel.setStyleSheet('padding: 7px 10px;' if dense else '')
        self.details.setStyleSheet('padding: 7px 10px;' if dense else '')
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
            self.render(self.bound_task, self.dense)


class MissionDeck(QFrame):
    """Two visible full cards, one selectable compact card; all share real IDs."""
    def __init__(self, controller, compact=False):
        super().__init__()
        self.controller, self.compact = controller, compact
        self.expanded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.count = QPushButton()
        self.count.setObjectName('quiet')
        self.count.clicked.connect(self.next_mission if compact else controller.mission_details_requested.emit)
        layout.addWidget(self.count)
        self.panels = [MissionPanel(controller, compact) for _ in range(1 if compact else 2)]
        for panel in self.panels:
            layout.addWidget(panel)
        self.hide()

    def __getattr__(self, name):
        panels = self.__dict__.get('panels')
        if panels and name in {'cancel', 'current', 'state', 'summary', 'dismiss', 'steps', 'opacity', 'fade'}:
            return getattr(panels[0], name)
        raise AttributeError(name)

    def next_mission(self):
        missions = [m for m in self.controller.mission_list() if m['status'] in EXPANDED_STATES]
        if len(missions) > 1:
            current = next((i for i, m in enumerate(missions) if m['id'] == self.controller.selected_mission_id), 0)
            self.controller.select_mission(missions[(current + 1) % len(missions)]['id'])

    def render(self):
        missions = self.controller.focus_missions()
        active = [m for m in missions if m['status'] in EXPANDED_STATES]
        count = len(active)
        self.count.setVisible(count > 1)
        self.count.setText(f'{count} missions actives · Suivante ›' if self.compact else
                           f'{count} missions actives' + (f' · Voir les {count-2} autres →' if count > 2 else ' · Tout voir →'))
        self.expanded = bool(active)
        shown = False
        for index, panel in enumerate(self.panels):
            if index < len(missions):
                shown = panel.render(missions[index], dense=count > 1) or shown
            else:
                panel.hide()
        self.setVisible(shown)
        return shown
