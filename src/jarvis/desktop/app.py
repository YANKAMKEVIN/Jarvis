"""Voice-only desktop companion; typed commands remain in the separate CLI."""
from __future__ import annotations

import math
import signal

from PySide6.QtCore import QObject, QPointF, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient, QShortcut, QLinearGradient
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

STYLE = """
QWidget { background: transparent; color: #dce8f6; font-family: '.AppleSystemUIFont', 'Inter', 'DejaVu Sans'; font-size: 13px; }
QMainWindow { background: #0b111b; }
QWidget#shell { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #152334, stop:0.42 #0d1622, stop:1 #0a1019); }
QLabel#wordmark { color: #e4f3ff; font-size: 18px; font-weight: 600; }
QLabel#greeting { color: #eef7ff; font-size: 26px; font-weight: 500; }
QLabel#intro { color: #94abc1; font-size: 14px; }
QLabel#status { color: #a4cbe7; font-size: 12px; }
QPushButton#quiet { background: transparent; border: 1px solid #304659; color: #a7c1d6; }

QLabel { background: transparent; }
QLabel#eyebrow { color: #7794af; font-size: 10px; font-weight: 600; }
QLabel#title { font-size: 27px; font-weight: 600; }
QLabel#subtitle { color: #91a9c1; font-size: 12px; }
QFrame#sidebar { background: rgba(10, 18, 29, 170); border-right: 1px solid #223044; }
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


class Controller(QObject):
    changed = Signal()
    exit_ready = Signal()

    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.reduced_motion = False
        self.voice_worker = None
        self.voice_state = "off"
        self.voice_mic_open = False
        self.input_suppressed = False
        self.voice_error = ""
        self.voice_turns = 0
        self.quit_after_voice = False

    def start_voice(self):
        if self.demo or self.voice_worker is not None:
            return
        from jarvis.desktop.live_runtime import VoiceSetupError, preload_live_plugins
        self.voice_state, self.voice_error = "starting", ""
        self.voice_turns = 0
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
        self.voice_mic_open = False
        self.input_suppressed = False
        worker.event.connect(self.voice_event)
        worker.finished.connect(lambda: self.voice_finished(worker))
        self.changed.emit()
        worker.start()

    def stop_voice(self):
        if self.voice_worker is not None:
            self.voice_state = "stopping"
            self.voice_worker.stop()
            self.changed.emit()

    def voice_event(self, event):
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
            self.changed.emit()

    def voice_finished(self, worker):
        if self.voice_worker is worker:
            self.voice_worker = None
            self.voice_mic_open = False
            self.input_suppressed = False
            if self.voice_state != "error":
                self.voice_state = "off"
            self.changed.emit()
        worker.deleteLater()
        if self.quit_after_voice:
            self.exit_ready.emit()

    def toggle_microphone(self):
        if self.voice_worker and self.voice_state not in {"starting", "stopping"}:
            self.voice_worker.set_muted(self.voice_mic_open)

    def interrupt_voice(self):
        if self.voice_worker and self.voice_state not in {"starting", "stopping"}:
            self.voice_worker.interrupt()


class VoicePanel(QWidget):
    def __init__(self, controller, compact=False):
        super().__init__()
        self.controller = controller
        self.compact = compact
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addStretch(1)
        self.orb = Orb(180 if compact else 280)
        layout.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        self.status = label("Votre assistant vocal", "greeting")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if compact:
            self.status.setStyleSheet("font-size: 21px;")
        layout.addWidget(self.status)
        self.hint = label("Parlez-moi simplement.", "intro")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint)
        layout.addStretch(2)
        controls = QHBoxLayout()
        self.voice_button = button("Démarrer Jarvis", self.toggle_voice, True)
        self.voice_button.setAccessibleName("Démarrer ou arrêter l’assistant vocal")
        controls.addWidget(self.voice_button)
        self.mic_button = button("Couper le micro", controller.toggle_microphone)
        controls.addWidget(self.mic_button)
        self.interrupt_button = button("Interrompre", controller.interrupt_voice)
        self.interrupt_button.setToolTip("Couper la réponse orale pour reprendre la parole. Les actions système déjà lancées peuvent continuer.")
        controls.addWidget(self.interrupt_button)
        layout.addLayout(controls)
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

    def render(self):
        c = self.controller
        active = c.voice_worker is not None
        state = c.voice_state
        self.orb.busy = state in {"thinking", "speaking"}
        self.orb.error = state == "error"
        self.orb.set_motion(not c.reduced_motion)
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
        self.voice_button.setText("Arrêt en cours…" if state == "stopping" else "Arrêter" if active else "Démarrer Jarvis")
        self.voice_button.setEnabled(not c.demo and state not in {"starting", "stopping"})
        for control in (self.mic_button, self.interrupt_button):
            control.setVisible(active)
            control.setEnabled(active and state not in {"starting", "stopping"})
        self.mic_button.setText("Couper le micro" if c.voice_mic_open else "Réactiver le micro")
        if c.voice_error:
            notice = c.voice_error
        elif c.demo:
            notice = "Démonstration visuelle · micro désactivé"
        elif c.input_suppressed:
            notice = "Écoute en pause pendant la réponse de Jarvis"
        elif c.voice_mic_open:
            notice = "Micro ouvert · voix envoyée à Gemini"
        elif active:
            notice = "Micro fermé"
        else:
            notice = "Le micro s’ouvre uniquement après votre activation."
        self.voice_notice.setText(notice)
        self.voice_notice.setStyleSheet("color: #e5a0aa;" if c.voice_error else "color: #91a9c1;")
        self.footnote.setText("JARVIS · ASSISTANT VOCAL" if not active else "GEMINI LIVE · CONFIRMATIONS VOCALES")


class DesktopWindow(QMainWindow):
    def __init__(self, controller, shell, compact=False):
        super().__init__()
        self.shell = shell
        self.controller = controller
        self.compact = compact
        self.setWindowTitle("Jarvis · " + ("Compagnon" if compact else "Assistant vocal"))
        self.resize(460, 520) if compact else self.resize(1080, 760)
        self.setMinimumSize(420, 510) if compact else self.setMinimumSize(800, 650)
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
            nav.addWidget(label("ASSISTANT VOCAL", "eyebrow"))
            nav.addSpacing(34)
            self.nav = []
            for i, text in enumerate(("Assistant", "Activité", "Réglages")):
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
        workspace.setContentsMargins(22 if compact else 32, 22, 22 if compact else 32, 22)
        workspace.setSpacing(16)
        heading = QHBoxLayout()
        heading.addWidget(label("J A R V I S" if compact else "VOTRE COMPAGNON", "eyebrow"))
        heading.addStretch()
        switch = button("Agrandir ↗" if compact else "Mode compact ↙", shell.switch_view)
        switch.setObjectName("quiet")
        heading.addWidget(switch)
        workspace.addLayout(heading)
        self.pages = QStackedWidget()
        self.assistant = VoicePanel(controller, compact)
        self.pages.addWidget(self.assistant)
        if not compact:
            self.activity = QWidget()
            info = QVBoxLayout(self.activity)
            info.setContentsMargins(0, 0, 0, 0)
            self.activity_summary = label("", "intro")
            info.addWidget(card("SESSION VOCALE", "Aucun fil de messages. Les demandes se font à voix haute."))
            info.addWidget(self.activity_summary)
            info.addStretch()
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
            reduce.toggled.connect(self.set_reduced_motion)
            settings_layout.addWidget(reduce)
            settings_layout.addWidget(label("⌘⇧Espace : mode compact lorsque Jarvis est actif.", "subtitle"))
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

    def render_activity(self):
        c = self.controller
        state = "En cours" if c.voice_worker else "Arrêtée"
        self.activity_summary.setText(f"Session : {state}\nDemandes vocales reçues : {c.voice_turns}")

    def closeEvent(self, event):
        event.ignore()
        if self.shell.has_tray:
            self.hide()
        else:
            self.shell.quit()


class DesktopShell:
    def __init__(self, app, controller):
        self.app, self.controller = app, controller
        self.has_tray = QSystemTrayIcon.isSystemTrayAvailable()
        controller.exit_ready.connect(app.quit)
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
        self.full.assistant.voice_button.setFocus()

    def show_compact(self):
        self.full.hide()
        self.compact.show()
        self.compact.raise_()
        self.compact.activateWindow()
        self.compact.assistant.voice_button.setFocus()

    def switch_view(self):
        self.show_full() if self.compact.isVisible() else self.show_compact()

    def quit(self):
        if self.controller.voice_worker:
            self.controller.quit_after_voice = True
            self.controller.stop_voice()
        else:
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
