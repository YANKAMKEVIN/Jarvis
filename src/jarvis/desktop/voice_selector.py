"""Assign voices without replacing an active session or opening the microphone."""
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)
from jarvis.desktop.appearances import CATALOG, BY_ID
from jarvis.desktop.avatar_assets import pose_image
from jarvis.desktop.voices import VOICES


class VoiceSelector(QDialog):
    def __init__(self, shell, parent=None):
        super().__init__(parent)
        self.shell, self.controller = shell, shell.controller
        self.setWindowTitle('Voix des avatars')
        self.setStyleSheet('QDialog, QListWidget { background: #0d1c2b; color: #e4f4ff; } '
                           'QListWidget::item:selected { background: #29485f; border: 1px solid #83cfff; }')
        self.resize(730, 630)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)
        title = QLabel('Une voix pour chaque compagnon')
        title.setStyleSheet('font-size: 23px; font-weight: 600;')
        layout.addWidget(title)
        intro = QLabel('Plusieurs avatars peuvent partager la même voix. Vos choix sont enregistrés automatiquement.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        body = QHBoxLayout()
        self.avatars = QListWidget()
        self.avatars.setAccessibleName('Avatar dont vous souhaitez choisir la voix')
        self.avatars.setIconSize(QSize(44, 44))
        self.avatars.setMinimumWidth(260)
        for avatar in CATALOG:
            item = QListWidgetItem(QIcon(QPixmap.fromImage(pose_image(avatar.id))), avatar.name)
            item.setData(Qt.ItemDataRole.UserRole, avatar.id)
            self.avatars.addItem(item)
        body.addWidget(self.avatars, 1)
        right = QVBoxLayout()
        self.portrait = QLabel()
        self.portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.portrait.setMinimumHeight(190)
        right.addWidget(self.portrait)
        self.name = QLabel()
        self.name.setStyleSheet('font-size: 20px; font-weight: 600;')
        right.addWidget(self.name)
        right.addWidget(QLabel('Voix de cet avatar'))
        self.voices = QComboBox()
        self.voices.setAccessibleName('Voix attribuée à cet avatar')
        for voice in VOICES:
            self.voices.addItem(f'{voice.id} · {voice.description}', voice.id)
        right.addWidget(self.voices)
        self.saved = QLabel()
        self.saved.setWordWrap(True)
        right.addWidget(self.saved)
        self.reset = QPushButton('Rétablir la voix initiale de cet avatar')
        self.reset.clicked.connect(self.reset_voice)
        right.addWidget(self.reset)
        self.listen = QPushButton('Écouter les voix dans Google AI Studio ↗')
        self.listen.setToolTip('Ouvre le catalogue vocal de Google dans votre navigateur.')
        self.listen.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://aistudio.google.com/')))
        right.addWidget(self.listen)
        right.addStretch()
        body.addLayout(right, 2)
        layout.addLayout(body, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('Fermer')
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.avatars.currentItemChanged.connect(self.select_avatar)
        self.voices.currentIndexChanged.connect(self.choose_voice)
        self.controller.changed.connect(self.render_status)
        self.controller.appearance_changed.connect(self.follow_avatar)
        self.follow_avatar(self.controller.appearance)
        self.render_status()

    def follow_avatar(self, appearance):
        for row in range(self.avatars.count()):
            if self.avatars.item(row).data(Qt.ItemDataRole.UserRole) == appearance:
                self.avatars.setCurrentRow(row)
                break

    def selected_avatar(self):
        return self.avatars.currentItem().data(Qt.ItemDataRole.UserRole)

    def select_avatar(self, *_):
        avatar = self.selected_avatar()
        self.name.setText(BY_ID[avatar].name)
        self.portrait.setPixmap(QPixmap.fromImage(pose_image(avatar)).scaled(
            190, 190, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.voices.blockSignals(True)
        self.voices.setCurrentIndex(self.voices.findData(self.shell.voice_preferences.load(avatar)))
        self.voices.blockSignals(False)
        self.saved.setText('Voix enregistrée pour cet avatar.')

    def choose_voice(self, _):
        self.shell.set_avatar_voice(self.selected_avatar(), self.voices.currentData())
        self.saved.setText('Votre choix est enregistré.')

    def reset_voice(self):
        avatar = self.selected_avatar()
        voice = self.shell.voice_preferences.reset(avatar)
        self.shell.set_avatar_voice(avatar, voice)
        self.select_avatar()

    def render_status(self):
        c = self.controller
        if c.voice_worker is not None:
            active = c.session_voice or 'Voix de la session'
            pending = c.selected_voice
            self.status.setText(f'Session en cours : {active}. ' +
                (f'Prochaine connexion : {pending}. ' if active != pending else '') +
                'Les changements de voix prendront effet à la prochaine connexion vocale.')
        else:
            self.status.setText(f'Avatar actuel : {BY_ID[c.appearance].name} · {c.selected_voice}. '
                                'Cette voix sera utilisée au prochain démarrage du vocal.')
