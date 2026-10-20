"""Small, draggable voice presence. Clicking never starts a microphone."""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget
from jarvis.desktop.visuals import Orb


class InteractiveOrb(Orb):
    def __init__(self, window):
        super().__init__(180)
        self.window_owner = window
        self.origin = self.press = None
        self.dragged = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Ouvrir le compagnon Jarvis ; faire glisser pour déplacer')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press = event.globalPosition().toPoint()
            self.origin = self.window_owner.pos()
            self.dragged = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self.press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            offset = event.globalPosition().toPoint() - self.press
            if offset.manhattanLength() >= QApplication.startDragDistance():
                self.dragged = True
            if self.dragged:
                self.window_owner.move(self.origin + offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.press is not None:
            self.press = None
            self.window_owner.shell.remember_orb()
            if not self.dragged:
                self.window_owner.shell.show_compact()
            event.accept()

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Escape}:
            self.window_owner.shell.show_compact()
            event.accept()
        else:
            super().keyPressEvent(event)


class OrbWindow(QWidget):
    def __init__(self, controller, shell):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.controller, self.shell = controller, shell
        self.assistant = self
        self.setWindowTitle('Jarvis · Orbe')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(188, 224)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 6)
        layout.setSpacing(0)
        self.orb = InteractiveOrb(self)
        layout.addWidget(self.orb)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet('background: rgba(12, 25, 39, 235); border: 1px solid #304d62; border-radius: 12px; padding: 6px; font-size: 11px; color: #bbdfef;')
        layout.addWidget(self.status)
        controller.audio_levels.connect(self.orb.set_levels)
        controller.changed.connect(self.render)
        self.shortcut = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
        self.shortcut.activated.connect(shell.show_compact)
        self.render()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.end()

    def render(self):
        c = self.controller
        self.orb.set_appearance(c.appearance)
        self.orb.state = c.avatar_state()
        self.orb.set_motion(not c.reduced_motion)
        self.orb.update()
        states = {'off': 'Micro fermé', 'starting': 'Connexion…', 'listening': 'En écoute',
                  'speaking': 'Réponse de Jarvis', 'thinking': 'Réflexion…', 'muted': 'Micro coupé',
                  'stopping': 'Arrêt…', 'error': 'Vocal indisponible'}
        state = states.get(c.voice_state, 'Jarvis')
        if c.input_suppressed:
            state = 'Écoute en pause'
        if c.screen_operations and c.voice_state not in {'off', 'error', 'stopping'}:
            state = 'Observation d’écran'
        if c.audio_worker is not None:
            state = 'Test micro local' if c.local_mic_open else 'Préparation audio' if c.audio_job_state == 'preparing' else 'Audio local'
        if c.demo:
            state = 'Démo · micro fermé'
        count = len(c.cards)
        self.status.setText(state + (f' · {count} carte(s)' if count else ''))
        self.setToolTip(state + '\nCliquer pour ouvrir · glisser pour déplacer · clic droit pour les commandes')

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for title, callback in (('Ouvrir le compagnon', self.shell.show_compact),
                                ('Ouvrir les détails', self.shell.show_details),
                                ('Fenêtre complète', self.shell.show_full)):
            menu.addAction(title, callback)
        menu.addAction('Choisir une apparence…', self.shell.show_appearances)
        menu.addSeparator()
        active = self.controller.voice_worker is not None
        action = menu.addAction('Arrêter le vocal' if active else 'Reconnecter' if self.controller.can_reconnect else 'Démarrer Jarvis',
                                self.controller.stop_voice if active else self.controller.start_voice)
        action.setEnabled(not self.controller.demo and self.controller.voice_state not in {'starting', 'stopping'} and self.controller.audio_worker is None)
        if active:
            menu.addAction('Couper le micro' if self.controller.voice_mic_open else 'Réactiver le micro', self.controller.toggle_microphone)
            menu.addAction('Interrompre la réponse', self.controller.interrupt_voice)
        menu.addSeparator()
        menu.addAction('Quitter Jarvis', self.shell.quit)
        menu.exec(event.globalPos())
        menu.deleteLater()

    def closeEvent(self, event):
        self.shell.remember_orb()
        self.shell.finish_transfer()
        event.ignore()
        if self.shell.has_tray:
            self.hide()
        else:
            self.shell.quit()
