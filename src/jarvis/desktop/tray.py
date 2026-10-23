"""Persistent menu controls driven by the shared voice controller."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu


def presence(controller):
    """A bounded status: never include tool payloads, transcripts or errors."""
    c = controller
    if c.local_mic_open:
        return 'Test micro local · micro ouvert', '#87dcff', True
    if c.audio_worker is not None:
        if c.audio_job_kind == 'voice_preview':
            return 'Aperçu vocal · micro fermé', '#aebdd0', False
        return 'Test audio local' if c.audio_job_kind != 'scan' else 'Lecture des périphériques', '#aebdd0', False
    state = c.voice_state
    if state == 'error':
        return 'Connexion interrompue' if c.can_reconnect else 'Vocal indisponible', '#ee99b9', False
    if state == 'stopping':
        return 'Arrêt en cours', '#aebdd0', c.voice_mic_open
    if state == 'starting':
        return 'Reconnexion…' if c.reconnecting else 'Connexion…', '#aebdd0', False
    if c.screen_operations:
        return 'Observation d’écran en cours', '#c5adff', c.voice_mic_open
    if state == 'speaking':
        return 'Jarvis répond · écoute suspendue', '#c5adff', c.voice_mic_open
    if state == 'thinking':
        return 'Jarvis réfléchit', '#c5adff', c.voice_mic_open
    if c.voice_mic_open:
        return ('Écoute suspendue' if c.input_suppressed else 'À votre écoute'), '#87dcff', True
    if c.voice_worker is not None:
        return 'Micro coupé · session ouverte', '#aebdd0', False
    return ('Démo · micro fermé' if c.demo else 'Au repos · micro fermé'), '#aebdd0', False


def presence_icon(color, microphone):
    pixmap = QPixmap(44, 44)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 3))
    painter.drawEllipse(5, 5, 34, 34)
    painter.setBrush(QColor(color))
    painter.drawEllipse(16, 16, 12, 12)
    if not microphone:
        painter.drawLine(9, 35, 35, 9)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class TrayControls:
    def __init__(self, shell, tray):
        self.shell, self.controller, self.tray = shell, shell.controller, tray
        # QSystemTrayIcon does not own its menu. Keep both a QWidget parent
        # and this Python reference throughout the lifetime of the shell.
        self.menu = QMenu(shell.full)
        self.status = self.action('')
        self.status.setEnabled(False)
        self.microphone_status = self.action('')
        self.microphone_status.setEnabled(False)
        self.menu.addSeparator()
        self.session = self.action('', self.toggle_session)
        self.microphone = self.action('', self.controller.toggle_microphone)
        self.interrupt = self.action('Interrompre la réponse', self.controller.interrupt_voice)
        self.stop_test = self.action('Arrêter le test audio local', self.controller.stop_audio_job)
        self.menu.addSeparator()
        self.action('Ouvrir Jarvis', shell.show_full)
        self.action('Compagnon compact', shell.show_compact)
        self.action('Orbe seul', shell.show_orb)
        self.action('Cartes et activité', shell.show_details)
        self.action('Réglages audio', shell.show_settings)
        self.action('Voix des avatars…', shell.show_voices)
        if hasattr(shell, 'settings'):
            self.action('Jarvis au quotidien…', lambda: shell.experience.open())
            self.action('Commandes · ⌘K', lambda: shell.experience.palette())
        self.action('Consommation (tokens)…', shell.show_usage)
        self.action('Activité machine…', shell.show_metrics)
        self.insights = None
        if hasattr(shell, 'set_insights_enabled'):
            self.insights = self.action('Alertes d’anomalies')
            self.insights.setCheckable(True)
            self.insights.setChecked(bool(getattr(shell, 'insights_enabled', True)))
            self.insights.toggled.connect(lambda checked: shell.set_insights_enabled(checked))
            self.insights_spoken = self.action('Annoncer les alertes à voix haute')
            self.insights_spoken.setCheckable(True)
            self.insights_spoken.setChecked(bool(getattr(shell, 'insights_spoken', True)))
            self.insights_spoken.toggled.connect(lambda checked: shell.set_insights_spoken(checked))
        self.action('Masquer les fenêtres', shell.hide_windows)
        self.menu.addSeparator()
        self.action('Quitter Jarvis', shell.quit)
        self.icon_state = None
        tray.setContextMenu(self.menu)
        self.controller.changed.connect(self.refresh)
        self.menu.aboutToShow.connect(self.refresh)
        self.refresh()

    def action(self, title, callback=None):
        action = QAction(title, self.menu)
        if callback is not None:
            action.triggered.connect(callback)
        self.menu.addAction(action)
        return action

    def toggle_session(self):
        c = self.controller
        if c.demo or c.audio_worker is not None or c.voice_state in {'starting', 'stopping'}:
            return
        if c.voice_worker is not None:
            if c.voice_state != 'error':
                c.stop_voice()
        else:
            c.start_voice()

    def refresh(self):
        c = self.controller
        status, color, capturing = presence(c)
        self.status.setText(status)
        self.microphone_status.setText('Capture micro ouverte' if capturing else 'Capture micro fermée')
        self.tray.setToolTip('Jarvis · ' + status)
        icon_state = (color, capturing)
        if icon_state != self.icon_state:
            self.tray.setIcon(presence_icon(*icon_state))
            self.icon_state = icon_state
        active = c.voice_worker is not None
        blocked = c.voice_state in {'starting', 'stopping'} or (active and c.voice_state == 'error')
        title = ('Fermeture…' if active and c.voice_state == 'error' else
                 'Connexion…' if c.voice_state == 'starting' else
                 'Arrêt en cours…' if c.voice_state == 'stopping' else
                 'Arrêter le vocal' if active else
                 'Reconnecter' if c.can_reconnect else
                 'Réessayer' if c.voice_state == 'error' else 'Démarrer le vocal')
        self.session.setText(title)
        self.session.setEnabled(not c.demo and c.audio_worker is None and not blocked)
        self.microphone.setText('Couper le micro' if c.voice_mic_open else 'Réactiver le micro')
        self.microphone.setEnabled(active and not blocked and not c.demo)
        self.interrupt.setEnabled(active and not blocked and not c.demo and c.voice_state in {'speaking', 'thinking'})
        self.stop_test.setText('Arrêter l’aperçu vocal' if c.audio_job_kind == 'voice_preview' else 'Arrêter le test audio local')
        self.stop_test.setVisible(c.audio_worker is not None)
        self.stop_test.setEnabled(c.audio_worker is not None and not c.demo)
