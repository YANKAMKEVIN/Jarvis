"""Read-only context cards and real action/task progress. No conversation feed."""
from urllib.parse import urlsplit
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from jarvis.desktop.presentation import STATUS_TEXT, TASK_TEXT, safe_url


def text(value, name=None):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name:
        widget.setObjectName(name)
    return widget


def box():
    frame = QFrame()
    frame.setObjectName('card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    return frame, layout


class DetailPanel(QWidget):
    def __init__(self, controller, activity=False):
        super().__init__()
        self.controller, self.activity = controller, activity
        self.signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(text('Suivi des actions' if activity else 'Vos cartes', 'greeting'))
        header.addStretch()
        self.clear = QPushButton('Effacer l’activité' if activity else 'Masquer les cartes')
        self.clear.clicked.connect(controller.clear_activity if activity else controller.clear_cards)
        header.addWidget(self.clear)
        layout.addLayout(header)
        layout.addWidget(text('Actions et tâches de cette session' if activity else
                              'Résultats d’outils · conservés uniquement dans cette session', 'subtitle'))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.rows = QVBoxLayout(self.content)
        self.rows.setContentsMargins(0, 8, 4, 0)
        self.rows.setSpacing(12)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        controller.changed.connect(self.render)
        self.render()

    def render(self):
        c = self.controller
        can_cancel = bool(c.voice_worker) and c.voice_state not in {'starting', 'stopping'}
        signature = repr((c.task, c.activity if self.activity else c.cards, can_cancel))
        if signature == self.signature:
            return
        self.signature = signature
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if c.task:
            frame, row = box()
            task = c.task
            row.addWidget(text(TASK_TEXT.get(task['status'], TASK_TEXT['unknown']), 'wordmark'))
            row.addWidget(text(f"{task['step_count']} étape(s) traitée(s)", 'subtitle'))
            for step in task['steps']:
                row.addWidget(text(f"{step['label']} · {STATUS_TEXT.get(step['status'], '')}"))
            if task['status'] in {'running', 'cancelling'}:
                row.addWidget(text('Une action déjà lancée peut finir avant l’arrêt.', 'subtitle'))
                cancel = QPushButton('Annulation demandée…' if task['status'] == 'cancelling' else 'Annuler la tâche')
                cancel.setObjectName('cancelTask')
                cancel.setEnabled(task['status'] == 'running' and can_cancel and not c.demo)
                cancel.clicked.connect(c.cancel_task)
                row.addWidget(cancel)
            self.rows.addWidget(frame)
        entries = list(c.activity.values() if self.activity else c.cards.values())
        for entry in reversed(entries):
            frame, row = box()
            if self.activity:
                row.addWidget(text(entry['label'], 'wordmark'))
                status = text(STATUS_TEXT.get(entry['status'], STATUS_TEXT['unknown']))
                status.setStyleSheet('color: #efb0bd;' if entry['status'] == 'error' else 'color: #a7daef;')
                row.addWidget(status)
                row.addWidget(text(entry['time'], 'eyebrow'))
            else:
                row.addWidget(text(entry['title'], 'wordmark'))
                row.addWidget(text('Résultat reçu à ' + entry['time'], 'eyebrow'))
                if entry['body']:
                    row.addWidget(text(entry['body']))
                for item in entry['items']:
                    row.addWidget(text('•  ' + item))
                for index, source in enumerate(entry['sources'], 1):
                    url = safe_url(source['url'])
                    if not url:
                        continue
                    row.addWidget(text(source['title'], 'subtitle'))
                    link = QPushButton(f"{index}. {urlsplit(url).hostname} ↗")
                    link.setToolTip(url)
                    link.setAccessibleName('Ouvrir la source : ' + source['title'])
                    link.clicked.connect(lambda checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
                    row.addWidget(link)
            self.rows.addWidget(frame)
        if not entries and not c.task:
            frame, row = box()
            row.addWidget(text('Tout commence par votre voix', 'wordmark'))
            row.addWidget(text('Demandez votre agenda, vos rappels ou une recherche web. Les résultats disponibles apparaîtront ici.' if not self.activity else
                               'Les outils réellement utilisés et les étapes des tâches apparaîtront ici.'))
            self.rows.addWidget(frame)
        self.rows.addStretch()
        self.clear.setEnabled(bool(entries) and (not self.activity or not any(e['status'] == 'running' for e in entries)))
