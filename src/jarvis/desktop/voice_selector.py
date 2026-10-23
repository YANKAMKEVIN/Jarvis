"""Assign voices without replacing an active session or opening the microphone."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QScrollArea, QWidget)
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
        self.resize(760, 740)
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
        self.search = QLineEdit()
        self.search.setPlaceholderText('Rechercher parmi les 30 voix…')
        self.search.setAccessibleName('Rechercher une voix par nom ou description')
        right.addWidget(self.search)
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
        self.favorite = QPushButton()
        self.favorite.clicked.connect(self.toggle_favorite)
        right.addWidget(self.favorite)
        self.listen = QPushButton('Écouter un aperçu')
        self.listen.clicked.connect(lambda: self.controller.start_voice_preview(self.voices.currentData()))
        right.addWidget(self.listen)
        self.stop = QPushButton('Arrêter l’aperçu')
        self.stop.clicked.connect(self.stop_preview)
        right.addWidget(self.stop)
        self.preview_message = 'Phrase fixe en français · générée par Gemini · micro fermé'
        self.preview_status = QLabel(self.preview_message)
        self.preview_status.setWordWrap(True)
        right.addWidget(self.preview_status)
        self.controller.audio_event.connect(self.preview_event)
        right.addStretch()
        right_content=QWidget();right_content.setLayout(right)
        right_scroll=QScrollArea();right_scroll.setWidgetResizable(True);right_scroll.setWidget(right_content)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.addWidget(right_scroll, 2)
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
        self.search.textChanged.connect(self.filter_voices)
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
        self.stop_preview()
        self.search.clear()
        avatar = self.selected_avatar()
        self.name.setText(BY_ID[avatar].name)
        self.portrait.setPixmap(QPixmap.fromImage(pose_image(avatar)).scaled(
            190, 190, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.populate_voices(self.shell.voice_preferences.load(avatar))
        self.saved.setText('Voix enregistrée pour cet avatar.')

    def choose_voice(self, _):
        self.stop_preview()
        self.shell.set_avatar_voice(self.selected_avatar(), self.voices.currentData())
        self.update_favorite()
        self.filter_voices(self.search.text())
        self.saved.setText('Votre choix est enregistré.')

    def reset_voice(self):
        avatar = self.selected_avatar()
        voice = self.shell.voice_preferences.reset(avatar)
        self.shell.set_avatar_voice(avatar, voice)
        self.select_avatar()

    def update_favorite(self):
        selected = self.voices.currentData() in self.shell.voice_preferences.favorites()
        self.favorite.setText('★ Retirer des favoris' if selected else '☆ Ajouter aux favoris')

    def populate_voices(self, current):
        favorites = self.shell.voice_preferences.favorites()
        self.voices.blockSignals(True)
        self.voices.clear()
        for voice in sorted(VOICES, key=lambda voice: voice.id not in favorites):
            prefix = '★ ' if voice.id in favorites else ''
            self.voices.addItem(f'{prefix}{voice.id} · {voice.description}', voice.id)
        self.voices.setCurrentIndex(self.voices.findData(current))
        self.voices.blockSignals(False)
        self.update_favorite()
        self.filter_voices(self.search.text())

    def toggle_favorite(self):
        current = self.voices.currentData()
        prefs = self.shell.voice_preferences
        prefs.set_favorite(current, current not in prefs.favorites())
        self.populate_voices(current)

    def filter_voices(self, text):
        # Keep the assigned voice visible even when it does not match the search.
        needle = text.casefold().strip()
        for index in range(self.voices.count()):
            item = self.voices.model().item(index)
            item.setEnabled(not needle or needle in self.voices.itemText(index).casefold() or index == self.voices.currentIndex())
            self.voices.view().setRowHidden(index, not item.isEnabled())

    def stop_preview(self):
        if self.controller.audio_worker is not None and self.controller.audio_job_kind == "voice_preview":
            self.controller.stop_audio_job()

    def preview_event(self, event):
        if event.get("kind") == "voice_preview":
            self.preview_message = event["message"]
            self.render_status()

    def hideEvent(self, event):
        self.stop_preview()
        super().hideEvent(event)

    def render_status(self):
        c = self.controller
        preview = c.audio_worker is not None and c.audio_job_kind == "voice_preview"
        self.listen.setEnabled(not c.demo and c.voice_worker is None and c.audio_worker is None)
        self.stop.setEnabled(preview)
        if c.demo:
            self.preview_status.setText("Démo · écoute désactivée. Lancez Jarvis sans --demo pour écouter les voix.")
        elif c.voice_worker is not None:
            self.preview_status.setText("Arrêtez le vocal pour écouter un aperçu sans ouvrir le micro.")
        else:
            self.preview_status.setText(self.preview_message)
        if c.voice_worker is not None:
            active = c.session_voice or 'Voix de la session'
            pending = c.selected_voice
            self.status.setText(f'Session en cours : {active}. ' +
                (f'Prochaine connexion : {pending}. ' if active != pending else '') +
                'Les changements de voix prendront effet à la prochaine connexion vocale.')
        else:
            self.status.setText(f'Avatar actuel : {BY_ID[c.appearance].name} · {c.selected_voice}. '
                                'Cette voix sera utilisée au prochain démarrage du vocal.')
