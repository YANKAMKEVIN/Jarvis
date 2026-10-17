"""Qt desktop shell; the existing executor remains the action boundary."""
from __future__ import annotations

import math
import signal
from types import SimpleNamespace
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QObject, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient, QShortcut, QLinearGradient
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from jarvis.desktop.session import DesktopSession, Job


STYLE = """
QWidget { background: transparent; color: #dce8f6; font-family: '.AppleSystemUIFont', 'Inter', 'DejaVu Sans'; font-size: 13px; }
QMainWindow { background: #0b111b; }
QWidget#shell { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #152334, stop:0.42 #0d1622, stop:1 #0a1019); }
QLabel#wordmark { color: #e4f3ff; font-size: 18px; font-weight: 600; }
QLabel#greeting { color: #eef7ff; font-size: 26px; font-weight: 500; }
QLabel#intro { color: #94abc1; font-size: 14px; }
QLabel#status { color: #a4cbe7; font-size: 12px; }
QFrame#userBubble { background: rgba(59, 101, 139, 65); border: 1px solid #30465b; border-radius: 16px; }
QFrame#assistantBubble { background: transparent; border: 0; }
QFrame#errorBubble { background: rgba(135, 45, 57, 35); border-left: 2px solid #cf7c87; border-radius: 8px; }
QPushButton#suggestion { background: rgba(37, 58, 80, 115); border: 1px solid #30475e; border-radius: 12px; text-align: left; padding: 15px; color: #c5d9eb; }
QPushButton#suggestion:hover { background: #253e55; border-color: #6b9bbd; }
QPushButton#quiet { background: transparent; border: 1px solid #304659; color: #a7c1d6; }
QPushButton#confirmAction { background: #e9bf7b; color: #211b10; border: 0; font-weight: 600; }
QPushButton#confirmAction:hover { background: #f6d59e; }

QLabel { background: transparent; }
QLabel#eyebrow { color: #7794af; font-size: 10px; font-weight: 600; }
QLabel#title { font-size: 27px; font-weight: 600; }
QLabel#subtitle { color: #91a9c1; font-size: 12px; }
QFrame#sidebar { background: rgba(10, 18, 29, 170); border-right: 1px solid #223044; }
QFrame#card { background: rgba(26, 43, 61, 155); border: 1px solid #293e52; border-radius: 16px; }
QFrame#confirmation { background: rgba(74, 57, 33, 95); border: 1px solid #8f7148; border-radius: 16px; }
QFrame#composer { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1b2d40, stop:1 #152335); border: 1px solid #405c75; border-radius: 16px; }
QLineEdit { background: transparent; border: 0; padding: 10px 4px; font-size: 14px; selection-background-color: #2c719f; }
QPushButton { background: #1a2a3d; border: 1px solid #2b435c; border-radius: 9px; padding: 10px 14px; }
QPushButton:hover { background: #243d57; border-color: #517ca2; }
QPushButton:focus { border: 1px solid #83cfff; }
QPushButton:disabled { color: #647b90; background: #152030; }
QPushButton#primary:hover { background: #b8e4ff; }
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


ACTION_LABELS = {
    "open_app": "Ouvrir une application", "close_app": "Fermer une application",
    "open_url": "Ouvrir un site", "web_search": "Rechercher sur le web",
    "set_volume": "Régler le volume", "mute": "Couper le son",
    "unmute": "Rétablir le son", "get_date": "Consulter la date",
}


def message_bubble(title, text, user=False, error=False):
    wrapper = QWidget()
    row = QHBoxLayout(wrapper)
    row.setContentsMargins(0, 0, 0, 0)
    if user:
        row.addStretch(1)
    frame = QFrame()
    frame.setObjectName("userBubble" if user else "errorBubble" if error else "assistantBubble")
    content = QVBoxLayout(frame)
    content.setContentsMargins(17, 13, 17, 13)
    content.setSpacing(8)
    heading = label(title, "eyebrow")
    if error:
        heading.setStyleSheet("color: #e5a0aa;")
    content.addWidget(heading)
    body = label(text)
    body.setStyleSheet("font-size: 14px;")
    body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    content.addWidget(body)
    row.addWidget(frame, 5)
    return wrapper


class Orb(QWidget):
    """Painted at device resolution, with no downloaded assets or web view."""
    def __init__(self, size=148):
        super().__init__()
        self.setFixedSize(size, size)
        self.phase = 0.0
        self.busy = False
        self.pending = False
        self.error = False
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
        radius = size * (0.29 + 0.008 * math.sin(self.phase * 2))
        accent = QColor("#edbd7b" if self.pending else "#dd8893" if self.error else "#86d6ff")
        glow = QColor(accent)
        glow.setAlpha(65)
        halo = QRadialGradient(center, size * 0.49)
        halo.setColorAt(0, glow)
        halo.setColorAt(0.65, QColor(accent.red(), accent.green(), accent.blue(), 22))
        halo.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(center, size * 0.49, size * 0.49)
        sphere = QRadialGradient(center - QPointF(radius * 0.3, radius * 0.5), radius * 1.8)
        sphere.setColorAt(0, accent.lighter(115))
        sphere.setColorAt(0.28, QColor("#4486ae") if not self.pending else QColor("#ad8753"))
        sphere.setColorAt(0.65, QColor("#122b46"))
        sphere.setColorAt(1, QColor("#070e1d"))
        painter.setBrush(sphere)
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 170), 1))
        painter.drawEllipse(center, radius, radius)
        clip = QPainterPath()
        clip.addEllipse(center, radius - 0.8, radius - 0.8)
        painter.save()
        painter.setClipPath(clip)
        painter.translate(center)
        # Flowing translucent ribbons replace the intersecting orbital rings.
        # These are decorative: no invented microphone or progress information.
        for index in range(4):
            painter.save()
            painter.rotate(index * 87 + self.phase * 14)
            wave = math.sin(self.phase + index) * radius * 0.12
            ribbon = QPainterPath(QPointF(-radius * 1.1, radius * 0.4))
            ribbon.cubicTo(-radius * 0.45, -radius * 0.95 + wave,
                           radius * 0.35, radius * 1.05, radius * 1.1, -radius * 0.35)
            ribbon.cubicTo(radius * 0.35, radius * 0.45 + wave,
                           -radius * 0.45, -radius * 0.45, -radius * 1.1, radius * 0.4)
            gradient = QLinearGradient(-radius, -radius, radius, radius)
            gradient.setColorAt(0, QColor(accent.red(), accent.green(), accent.blue(), 8))
            gradient.setColorAt(0.5, QColor(accent.red(), accent.green(), accent.blue(), 140))
            gradient.setColorAt(1, QColor(accent.red(), accent.green(), accent.blue(), 10))
            painter.setBrush(gradient)
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 90), 0.7))
            painter.drawPath(ribbon)
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
        self._render_key = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        hero = QHBoxLayout()
        self.orb = Orb(76 if compact else 180)
        hero.addStretch()
        hero.addWidget(self.orb)
        if compact:
            title = QVBoxLayout()
            title.addWidget(label("Jarvis", "wordmark"))
            self.status = label("À votre disposition", "status")
            title.addWidget(self.status)
            hero.addLayout(title)
        hero.addStretch()
        layout.addLayout(hero)
        if not compact:
            self.status = label("À votre disposition", "status")
            self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.messages = QVBoxLayout(self.body)
        self.messages.setContentsMargins(0, 0, 4, 0)
        self.messages.setSpacing(16)
        self.scroll.setWidget(self.body)
        self.opacity = QGraphicsOpacityEffect(self.body)
        self.opacity.setOpacity(1.0)
        self.body.setGraphicsEffect(self.opacity)
        self.fade = QPropertyAnimation(self.opacity, b"opacity", self)
        self.fade.setDuration(180)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        layout.addWidget(self.scroll, 1)
        composer = QFrame()
        composer.setObjectName("composer")
        shadow = QGraphicsDropShadowEffect(composer)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(0, 0, 0, 65))
        composer.setGraphicsEffect(shadow)
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
        self.footnote = label("DÉMO · aucune action réelle" if controller.demo else "Session privée · Réponses écrites", "subtitle")
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
        self.orb.pending = bool(session.pending)
        self.orb.error = bool(session.turns and session.turns[-1].status == "error")
        self.orb.set_motion(not self.controller.reduced_motion)
        self.status.setText("Traitement en cours…" if session.busy else
                            "Votre accord est nécessaire" if session.pending else "À votre disposition")
        self.status.setStyleSheet("color: #e8c18b;" if session.pending else
                                  "color: #e5a0aa;" if self.orb.error else "color: #a4cbe7;")
        self.input.setEnabled(not session.busy and not session.pending)
        self.send.setEnabled(not session.busy and not session.pending)
        while self.messages.count():
            item = self.messages.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        turns = session.turns[-1:] if self.compact else session.turns
        if not turns:
            welcome = QWidget()
            intro = QVBoxLayout(welcome)
            intro.setContentsMargins(4, 12 if self.compact else 22, 4, 12)
            intro.setSpacing(12)
            greeting = "Bonsoir." if datetime.now().hour >= 18 or datetime.now().hour < 6 else "Bonjour."
            title = label("À votre service." if self.compact else greeting + " Que fait-on aujourd’hui ?", "greeting")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self.compact:
                title.setStyleSheet("font-size: 20px;")
            intro.addWidget(title)
            description = label("Une idée, une question, une action. Je suis là.", "intro")
            description.setAlignment(Qt.AlignmentFlag.AlignCenter)
            intro.addWidget(description)
            if not self.compact:
                intro.addSpacing(12)
                suggestions = QHBoxLayout()
                for caption, prompt in (("Ouvrir Safari ↗", "Ouvre Safari"),
                                        ("Lancer une recherche", "Recherche sur le web "),
                                        ("Trouver une idée", "Donne-moi trois idées pour ")):
                    chip = button(caption, lambda checked=False, text=prompt: self.use_suggestion(text))
                    chip.setObjectName("suggestion")
                    chip.setToolTip("Préparer cette demande sans l’envoyer")
                    suggestions.addWidget(chip)
                intro.addLayout(suggestions)
            self.messages.addWidget(welcome)
        for turn in turns:
            self.messages.addWidget(message_bubble(f"VOUS · {turn.time}", turn.command, user=True))
            if turn.status != "confirmation" and (turn.reply or turn.status == "running"):
                headings = {"running": "JARVIS · EN COURS", "response": "JARVIS",
                            "error": "DEMANDE NON TERMINÉE", "cancelled": "ACTION ANNULÉE"}
                self.messages.addWidget(message_bubble(headings[turn.status],
                    "Je m’en occupe…" if turn.status == "running" else turn.reply,
                    error=turn.status == "error"))
        if session.pending:
            frame = QFrame()
            frame.setObjectName("confirmation")
            content = QVBoxLayout(frame)
            content.setContentsMargins(18, 16, 18, 16)
            title = label("VOTRE ACCORD", "eyebrow")
            title.setStyleSheet("color: #e8c18b;")
            content.addWidget(title)
            intent = session.pending.intent
            action_title = ACTION_LABELS.get(intent.action, intent.action)
            preview = label(f"{action_title}\n{intent.target or 'Aucune cible précisée'}")
            preview.setStyleSheet("font-size: 15px;")
            content.addWidget(preview)
            details = label(session.turns[-1].reply, "subtitle")
            content.addWidget(details)
            row = QHBoxLayout()
            row.addWidget(button("Annuler", self.controller.cancel))
            approve = button("Confirmer", self.controller.confirm)
            approve.setObjectName("confirmAction")
            row.addWidget(approve)
            content.addLayout(row)
            self.messages.addWidget(frame)
        self.messages.addStretch()
        key = tuple((turn.id, turn.status, turn.reply) for turn in turns)
        self.fade.stop()
        if key != self._render_key and self.isVisible() and not self.controller.reduced_motion:
            self.fade.setStartValue(0.7)
            self.fade.setEndValue(1.0)
            self.fade.start()
        else:
            self.opacity.setOpacity(1.0)
        self._render_key = key
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def use_suggestion(self, text):
        if self.controller.session.busy or self.controller.session.pending:
            return
        self.controller.set_draft(text)
        self.input.setFocus()
        self.input.setCursorPosition(len(text))


class DesktopWindow(QMainWindow):
    def __init__(self, controller, shell, compact=False):
        super().__init__()
        self.shell = shell
        self.controller = controller
        self.compact = compact
        self.setWindowTitle("Jarvis · " + ("Compagnon" if compact else "Espace personnel"))
        self.resize(460, 360) if compact else self.resize(1160, 790)
        self.setMinimumSize(420, 350) if compact else self.setMinimumSize(900, 650)
        if compact:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        root = QWidget()
        root.setObjectName("shell")
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
            nav.addWidget(label("●  SESSION PRIVÉE", "eyebrow"))
            nav.addWidget(label("Vos échanges restent dans cette session.", "subtitle"))
            row.addWidget(sidebar)
        workspace = QVBoxLayout()
        workspace.setContentsMargins(22 if compact else 32, 22, 22 if compact else 32, 22)
        workspace.setSpacing(16)
        heading = QHBoxLayout()
        heading.addWidget(label("J A R V I S" if compact else "VOTRE ESPACE", "eyebrow"))
        heading.addStretch()
        switch = button("Agrandir ↗" if compact else "Mode compact ↙", shell.switch_view)
        switch.setObjectName("quiet")
        heading.addWidget(switch)
        workspace.addLayout(heading)
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
        self.resize_animation = QPropertyAnimation(self, b"geometry", self)
        self.resize_animation.setDuration(240)
        self.resize_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        if compact:
            controller.changed.connect(self.fit_compact)

    def fit_compact(self, animate=True):
        if not self.compact:
            return
        session = self.controller.session
        if not session.turns:
            height = 360
        elif session.pending:
            height = 610
        else:
            text_length = len(session.turns[-1].command) + len(session.turns[-1].reply)
            height = min(680, 440 + (text_length // 65) * 20)
        available = self.screen().availableGeometry()
        height = min(height, available.height() - 48)
        height = max(height, self.minimumHeight())
        top = min(self.y(), available.bottom() - height - 32)
        top = max(available.top(), top)
        target = QRect(self.x(), top, self.width(), height)
        self.resize_animation.stop()
        if target == self.geometry():
            return
        if animate and self.isVisible() and not self.controller.reduced_motion:
            self.resize_animation.setStartValue(self.geometry())
            self.resize_animation.setEndValue(target)
            self.resize_animation.start()
        else:
            self.setGeometry(target)

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
            layout.addWidget(card("ACTIVITÉ DE CETTE SESSION", "Vos demandes et leurs réponses apparaîtront ici."))
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
        self.compact.fit_compact(animate=False)
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
