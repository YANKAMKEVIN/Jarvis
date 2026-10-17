"""Qt desktop shell; the existing executor remains the action boundary."""
from __future__ import annotations

import math
from types import SimpleNamespace

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QRadialGradient, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from jarvis.desktop.session import DesktopSession, Job


STYLE = """
QWidget { background: #0c121d; color: #dce8f6; font-family: '.AppleSystemUIFont', 'Inter', 'DejaVu Sans'; font-size: 13px; }
QMainWindow { background: #0c121d; }
QLabel { background: transparent; }
QLabel#eyebrow { color: #7794af; font-size: 10px; font-weight: 600; }
QLabel#title { font-size: 29px; font-weight: 600; }
QLabel#subtitle { color: #91a9c1; font-size: 12px; }
QFrame#sidebar { background: #101927; border-right: 1px solid #223044; }
QFrame#card { background: #131f2f; border: 1px solid #26394e; border-radius: 14px; }
QFrame#confirmation { background: #202335; border: 1px solid #a58350; border-radius: 14px; }
QFrame#composer { background: #152235; border: 1px solid #344d67; border-radius: 14px; }
QLineEdit { background: transparent; border: 0; padding: 10px 4px; font-size: 14px; selection-background-color: #2c719f; }
QPushButton { background: #1a2a3d; border: 1px solid #2b435c; border-radius: 9px; padding: 10px 14px; }
QPushButton:hover { background: #243d57; border-color: #517ca2; }
QPushButton:focus { border: 1px solid #83cfff; }
QPushButton:disabled { color: #647b90; background: #152030; }
QPushButton#primary { background: #82caff; color: #081421; border: 0; font-weight: 600; }
QPushButton#nav { text-align: left; background: transparent; border: 0; padding: 13px; color: #91a9c1; }
QPushButton#nav:checked { color: #e0f1ff; background: #22354b; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: #101927; width: 7px; }
QScrollBar::handle:vertical { background: #344c63; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { spacing: 10px; padding: 8px 0; }
QToolTip { background: #23384f; color: #e1efff; border: 1px solid #527494; }
QMenu { background: #152235; border: 1px solid #344d67; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #29435f; }
"""


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


class Orb(QWidget):
    """Painted at device resolution, with no downloaded assets or web view."""
    def __init__(self, size=148):
        super().__init__()
        self.setFixedSize(size, size)
        self.phase = 0.0
        self.busy = False
        self.motion = True
        self.setAccessibleName("État de Jarvis")
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)

    def showEvent(self, event):
        if self.motion:
            self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def set_motion(self, enabled):
        self.motion = enabled
        if enabled and self.isVisible():
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def tick(self):
        self.phase += 0.045 if self.busy else 0.014
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = self.width()
        center = QPointF(size / 2, size / 2)
        radius = size * (0.32 + 0.012 * math.sin(self.phase * 2))
        halo = QRadialGradient(center, size * 0.5)
        halo.setColorAt(0.0, QColor(32, 117, 213, 130))
        halo.setColorAt(0.68, QColor(30, 103, 202, 50))
        halo.setColorAt(1.0, QColor(30, 103, 202, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(center, size * 0.5, size * 0.5)
        sphere = QRadialGradient(center - QPointF(radius * 0.4, radius * 0.5), radius * 1.6)
        sphere.setColorAt(0, QColor("#8edbff"))
        sphere.setColorAt(0.28, QColor("#267bc6"))
        sphere.setColorAt(0.7, QColor("#10294e"))
        sphere.setColorAt(1, QColor("#06111e"))
        painter.setBrush(sphere)
        painter.setPen(QPen(QColor("#78c9ff"), 1.2))
        painter.drawEllipse(center, radius, radius)
        painter.save()
        painter.translate(center)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index in range(3):
            painter.save()
            painter.rotate(index * 58 + math.sin(self.phase) * 12)
            painter.setPen(QPen(QColor(145, 220, 255, 150), 1.1))
            painter.drawEllipse(QRectF(-radius, -radius * 0.38, radius * 2, radius * 0.76))
            painter.restore()
        painter.restore()


class ExecutionThread(QThread):
    delivered = Signal(object, object, object)

    def __init__(self, job, controller):
        super().__init__(controller)
        self.job = job
        self.controller = controller

    def run(self):
        try:
            result = self.controller.execute(self.job)
            self.delivered.emit(self.job, result, None)
        except Exception:
            # Exception strings can contain file contents, model payloads or
            # credentials. The UI gives actionable diagnostics without logging.
            self.delivered.emit(self.job, None,
                "Jarvis n’a pas pu terminer cette demande. Vérifiez Ollama, "
                "le modèle installé et les autorisations macOS. "
                "Une action peut avoir été partiellement exécutée : vérifiez avant de réessayer.")


class Controller(QObject):
    changed = Signal()
    draft_changed = Signal(str)

    def __init__(self, demo=False, executor=None):
        super().__init__()
        self.session = DesktopSession()
        self.demo = demo
        self.executor = executor
        self.workers = set()
        self.reduced_motion = False

    def execute(self, job):
        if self.demo:
            from jarvis.intents import Intent
            if job.intent is None:
                return SimpleNamespace(message="Simulation : cette action attend votre accord.",
                    needs_confirmation=True, intent=Intent("open_app", "Safari"))
            return SimpleNamespace(message="Simulation terminée. Aucune application n’a été ouverte.",
                needs_confirmation=False, intent=job.intent)
        if self.executor is None:
            from jarvis.executor import CommandExecutor
            self.executor = CommandExecutor()
        if job.intent is not None:
            return self.executor.execute_intent(job.intent, confirmed=True)
        return self.executor.execute(job.command)

    def set_draft(self, text):
        self.session.draft = text
        self.draft_changed.emit(text)

    def submit(self):
        if self.session.busy or self.session.pending or not self.session.draft.strip():
            return
        self.dispatch(self.session.begin(self.session.draft))
        self.draft_changed.emit("")

    def dispatch(self, job):
        worker = ExecutionThread(job, self)
        self.workers.add(worker)
        worker.delivered.connect(self.delivered)
        worker.finished.connect(lambda: self.release(worker))
        self.changed.emit()
        worker.start()

    def release(self, worker):
        self.workers.discard(worker)
        worker.deleteLater()

    def delivered(self, job, result, error):
        self.session.finish(job, result, error)
        self.changed.emit()

    def confirm(self):
        if self.session.pending and not self.session.busy:
            self.dispatch(self.session.confirm())

    def cancel(self):
        self.session.cancel()
        self.changed.emit()

    def clear(self):
        self.session.clear()
        self.draft_changed.emit("")
        self.changed.emit()


class Conversation(QWidget):
    def __init__(self, controller, compact=False):
        super().__init__()
        self.controller = controller
        self.compact = compact
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        hero = QHBoxLayout()
        self.orb = Orb(66 if compact else 148)
        hero.addStretch()
        hero.addWidget(self.orb)
        if compact:
            title = QVBoxLayout()
            title.addWidget(label("Jarvis"))
            self.status = label("À votre disposition", "subtitle")
            title.addWidget(self.status)
            hero.addLayout(title)
        hero.addStretch()
        layout.addLayout(hero)
        if not compact:
            self.status = label("À votre disposition", "subtitle")
            self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.messages = QVBoxLayout(self.body)
        self.messages.setContentsMargins(0, 0, 4, 0)
        self.messages.setSpacing(12)
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)
        composer = QFrame()
        composer.setObjectName("composer")
        row = QHBoxLayout(composer)
        row.setContentsMargins(12, 7, 7, 7)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Demandez à Jarvis…")
        self.input.setAccessibleName("Votre demande à Jarvis")
        self.input.setMaxLength(8000)
        self.input.textEdited.connect(controller.set_draft)
        self.input.returnPressed.connect(controller.submit)
        row.addWidget(self.input, 1)
        self.send = button("Envoyer ↑", controller.submit, True)
        row.addWidget(self.send)
        layout.addWidget(composer)
        self.footnote = label("DÉMO · aucune action réelle" if controller.demo else "Moteur texte · Ollama local · vocal Live à connecter", "subtitle")
        layout.addWidget(self.footnote)
        controller.changed.connect(self.render)
        controller.draft_changed.connect(self.sync_draft)
        self.render()

    def sync_draft(self, text):
        if self.input.text() != text:
            self.input.setText(text)

    def render(self):
        session = self.controller.session
        self.orb.busy = session.busy
        self.orb.set_motion(not self.controller.reduced_motion)
        self.status.setText("Traitement en cours…" if session.busy else
                            "Votre accord est nécessaire" if session.pending else "À votre disposition")
        self.input.setEnabled(not session.busy and not session.pending)
        self.send.setEnabled(not session.busy and not session.pending)
        while self.messages.count():
            item = self.messages.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        turns = session.turns[-1:] if self.compact else session.turns
        if not turns:
            self.messages.addWidget(card("COMMENT PUIS-JE VOUS AIDER ?",
                "Écrivez une demande pour ouvrir une application, lancer une recherche ou poser une question."))
        for turn in turns:
            self.messages.addWidget(card(f"VOUS · {turn.time}", turn.command))
            if turn.reply or turn.status == "running":
                headings = {"running": "EN COURS", "response": "JARVIS · RÉPONSE",
                            "error": "DEMANDE NON TERMINÉE", "cancelled": "ANNULÉE",
                            "confirmation": "AVANT DE CONTINUER"}
                self.messages.addWidget(card(headings[turn.status],
                    "Jarvis traite votre demande…" if turn.status == "running" else turn.reply))
        if session.pending:
            frame = QFrame()
            frame.setObjectName("confirmation")
            content = QVBoxLayout(frame)
            content.setContentsMargins(18, 16, 18, 16)
            content.addWidget(label("CONFIRMER CETTE ACTION", "eyebrow"))
            content.addWidget(label(f"Action : {session.pending.intent.action}\nCible : {session.pending.intent.target or '—'}"))
            row = QHBoxLayout()
            row.addWidget(button("Annuler", self.controller.cancel))
            row.addWidget(button("Confirmer", self.controller.confirm, True))
            content.addLayout(row)
            self.messages.addWidget(frame)
        self.messages.addStretch()
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))


class DesktopWindow(QMainWindow):
    def __init__(self, controller, shell, compact=False):
        super().__init__()
        self.shell = shell
        self.controller = controller
        self.compact = compact
        self.setWindowTitle("Jarvis · " + ("Compagnon" if compact else "Espace personnel"))
        self.resize(460, 610) if compact else self.resize(1160, 790)
        self.setMinimumSize(420, 470) if compact else self.setMinimumSize(900, 650)
        if compact:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        root = QWidget()
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
            nav.addWidget(label("J A R V I S"))
            nav.addWidget(label("ESPACE PERSONNEL", "eyebrow"))
            nav.addSpacing(34)
            self.nav = []
            for i, text in enumerate(("Conversation", "Activité", "Réglages")):
                b = button(text, lambda checked=False, index=i: self.navigate(index))
                b.setObjectName("nav")
                b.setCheckable(True)
                self.nav.append(b)
                nav.addWidget(b)
            nav.addStretch()
            nav.addWidget(label("SESSION LOCALE\nHistorique en mémoire uniquement", "subtitle"))
            row.addWidget(sidebar)
        workspace = QVBoxLayout()
        workspace.setContentsMargins(22 if compact else 32, 22, 22 if compact else 32, 22)
        workspace.setSpacing(16)
        heading = QHBoxLayout()
        heading.addWidget(label("COMPAGNON" if compact else "VOTRE ASSISTANT PERSONNEL", "eyebrow"))
        heading.addStretch()
        heading.addWidget(button("Agrandir ↗" if compact else "Mode compact ↙", shell.switch_view))
        workspace.addLayout(heading)
        if not compact:
            workspace.addWidget(label("Un peu d’espace pour vos idées.", "title"))
        self.pages = QStackedWidget()
        self.conversation = Conversation(controller, compact)
        self.pages.addWidget(self.conversation)
        if not compact:
            self.activity = QScrollArea()
            self.activity.setWidgetResizable(True)
            self.pages.addWidget(self.activity)
            settings = QWidget()
            settings_layout = QVBoxLayout(settings)
            settings_layout.setContentsMargins(0, 0, 0, 0)
            settings_layout.addWidget(card("CONNEXION AU MOTEUR",
                "Mode démo : aucune action système." if controller.demo else
                "Moteur texte existant · Ollama sur localhost:11434.\nLe mode Gemini Live reste indépendant."))
            settings_layout.addWidget(card("CONFIDENTIALITÉ",
                "Cette interface garde les échanges en mémoire jusqu’à sa fermeture. "
                "Effacer la session réinitialise aussi le contexte du moteur texte. "
                "Les bases mémoire, rappels et journaux du moteur ne sont pas effacées."))
            reduce = QCheckBox("Réduire les animations")
            reduce.toggled.connect(self.set_reduced_motion)
            settings_layout.addWidget(reduce)
            self.clear_button = button("Effacer la session…", self.clear_session)
            settings_layout.addWidget(self.clear_button)
            settings_layout.addWidget(label("⌘⇧Espace : mode compact (lorsque Jarvis est actif).\n"
                "Le vocal, les routines et l’arrêt d’une action en cours seront intégrés ensuite.", "subtitle"))
            settings_layout.addStretch()
            self.pages.addWidget(settings)
            controller.changed.connect(self.render_activity)
            self.navigate(0)
            self.render_activity()
        workspace.addWidget(self.pages, 1)
        row.addLayout(workspace, 1)
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
        shortcut.activated.connect(shell.show_compact)

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, widget in enumerate(self.nav):
            widget.setChecked(index == i)

    def set_reduced_motion(self, checked):
        self.controller.reduced_motion = checked
        self.controller.changed.emit()

    def clear_session(self):
        if QMessageBox.question(self, "Effacer la session", "Effacer les échanges de cette session et le contexte du moteur texte ?") == QMessageBox.StandardButton.Yes:
            self.controller.clear()
            # Safe only while idle, enforced by the session and disabled button.
            self.controller.executor = None

    def render_activity(self):
        session = self.controller.session
        self.clear_button.setEnabled(not session.busy and not session.pending)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 4, 0)
        if not session.turns:
            layout.addWidget(card("ACTIVITÉ DE CETTE SESSION", "Vos demandes apparaîtront ici. Aucun historique fictif."))
        statuses = {"running": "En cours", "confirmation": "Accord attendu", "response": "Réponse reçue", "error": "Non terminée", "cancelled": "Annulée"}
        for turn in reversed(session.turns):
            layout.addWidget(card(f"{turn.time} · {statuses[turn.status]}", turn.command))
        layout.addStretch()
        old = self.activity.takeWidget()
        if old:
            old.deleteLater()
        self.activity.setWidget(body)

    def closeEvent(self, event):
        if self.shell.has_tray:
            event.ignore()
            self.hide()
        elif self.controller.session.busy or self.controller.workers:
            event.ignore()
            QMessageBox.information(self, "Demande en cours", "Attendez la fin du traitement avant de quitter.")
        else:
            self.shell.app.quit()
            event.accept()


class DesktopShell:
    def __init__(self, app, controller):
        self.app = app
        self.controller = controller
        self.has_tray = QSystemTrayIcon.isSystemTrayAvailable()
        self.full = DesktopWindow(controller, self)
        self.compact = DesktopWindow(controller, self, compact=True)
        self.tray = None
        if self.has_tray:
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor("#87d2ff"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(6, 6, 20, 20)
            painter.end()
            self.tray = QSystemTrayIcon(QIcon(pixmap), app)
            self.tray.setToolTip("Jarvis")
            menu = QMenu()
            for title, callback in (("Ouvrir Jarvis", self.show_full), ("Compagnon compact", self.show_compact), ("Quitter", self.quit)):
                action = QAction(title, menu)
                action.triggered.connect(callback)
                menu.addAction(action)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self.tray_activated)
            self.tray.show()
        app.setQuitOnLastWindowClosed(False)

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_compact()

    def show_full(self):
        self.compact.hide()
        self.full.show()
        self.full.raise_()
        self.full.activateWindow()
        self.full.conversation.input.setFocus()

    def show_compact(self):
        self.full.hide()
        self.compact.show()
        self.compact.raise_()
        self.compact.activateWindow()
        self.compact.conversation.input.setFocus()

    def switch_view(self):
        self.show_full() if self.compact.isVisible() else self.show_compact()

    def quit(self):
        if self.controller.session.busy or self.controller.workers:
            QMessageBox.information(self.full if self.full.isVisible() else self.compact,
                "Demande en cours", "Attendez la fin du traitement avant de quitter. L’arrêt forcé n’est pas encore disponible.")
            return
        self.app.quit()


def run(demo=False, compact=False):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Jarvis")
    app.setOrganizationName("Jarvis")
    app.setStyleSheet(STYLE)
    controller = Controller(demo=demo)
    shell = DesktopShell(app, controller)
    shell.show_compact() if compact else shell.show_full()
    return app.exec()
