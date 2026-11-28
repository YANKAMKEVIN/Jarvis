"""DesktopWindow: the main window with its navigation, shortcuts and settings pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.desktop.app_voice_panel import VoicePanel
from jarvis.desktop.app_widgets import button, label, section
from jarvis.desktop.audio_settings import AudioSettings
from jarvis.desktop.panels import DetailPanel
from jarvis.desktop.surfaces import DragHandle, GlassSurface, NavButton


class DesktopWindow(QMainWindow):
    def __init__(self, controller, shell, compact=False):
        super().__init__()
        self.shell = shell
        self.controller = controller
        self.compact = compact
        self.setWindowTitle("Jarvis · " + ("Compagnon" if compact else "Assistant vocal"))
        self.resize(460, 560) if compact else self.resize(1080, 800)
        self.setMinimumSize(440, 550) if compact else self.setMinimumSize(800, 730)
        if compact:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                                Qt.WindowType.WindowStaysOnTopHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setStyleSheet("QMainWindow { background: transparent; }")
        root = GlassSurface() if compact else QWidget()
        root.setObjectName("capsule" if compact else "shell")
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
            self.seen_cards = set()
            for i, (text, kind) in enumerate((("Assistant", "assistant"), ("Cartes", "cards"),
                                              ("Activité", "activity"), ("Réglages", "settings"))):
                b = NavButton(text, kind, f"⌘{i + 1}")
                b.clicked.connect(lambda checked=False, index=i: self.navigate(index))
                b.setToolTip(f"{text} · ⌘{i + 1}")
                self.nav.append(b)
                nav.addWidget(b)
            nav.addStretch()
            # Screens that already exist but were only reachable from the menu bar or the palette.
            nav.addWidget(label("OUTILS", "eyebrow"))
            self.tools = {}
            for key, text, tip, callback in (
                    ("dashboard", "Tableau de bord", "Usage, métriques et alertes", lambda: shell.show_dashboard()),
                    ("history", "Historique", "Missions et procédures retenues", lambda: shell.experience.history()),
                    ("memory", "Mémoire", "Mémoire et préférences retenues", lambda: shell.experience.memory()),
                    ("palette", "Palette  ⌘K", "Palette de commandes · ⌘K", lambda: shell.experience.palette())):
                b = button(text, lambda checked=False, run=callback: run())
                b.setObjectName("tool")
                b.setToolTip(tip)
                self.tools[key] = b
                nav.addWidget(b)
            row.addWidget(sidebar)
        workspace = QVBoxLayout()
        workspace.setContentsMargins(28 if compact else 40, 26, 28 if compact else 40, 28)
        workspace.setSpacing(16)
        heading = QHBoxLayout()
        # The sidebar already carries the wordmark: the header names the current page.
        self.page_title = None if compact else label("ASSISTANT", "eyebrow")
        heading.addWidget(DragHandle("◌   J A R V I S") if compact else self.page_title, 1)
        heading.addStretch()
        switch = button("Agrandir ↗" if compact else "Mode compact ↙", shell.switch_view)
        switch.setObjectName("quiet")
        heading.addWidget(switch)
        orb_mode = button('◉', shell.show_orb)
        orb_mode.setObjectName('quiet')
        orb_mode.setFixedSize(34, 34)
        orb_mode.setStyleSheet('padding: 0; font-size: 19px;')
        orb_mode.setToolTip('Mode orbe seul')
        orb_mode.setAccessibleName('Passer au mode orbe seul')
        heading.addWidget(orb_mode)
        if compact:
            close = button("×", self.close)
            close.setObjectName("quiet")
            close.setFixedSize(32, 32)
            close.setStyleSheet("padding: 0; font-size: 20px;")
            close.setAccessibleName("Fermer le compagnon")
            heading.addWidget(close)
        workspace.addLayout(heading)
        self.pages = QStackedWidget()
        self.assistant = VoicePanel(controller, compact)
        self.pages.addWidget(self.assistant)
        if not compact:
            self.cards_page = DetailPanel(controller)
            self.pages.addWidget(self.cards_page)
            self.activity = DetailPanel(controller, activity=True)
            self.pages.addWidget(self.activity)
            settings = QWidget()
            settings_layout = QVBoxLayout(settings)
            settings_layout.setContentsMargins(0, 0, 6, 0)
            settings_layout.setSpacing(14)
            settings_layout.addWidget(label("Réglages", "greeting"))

            voice = section("VOIX ET MICRO", settings_layout)
            self.wake_check = QCheckBox("Réveiller Jarvis en disant « Jarvis » (détection locale)")
            self.wake_check.setToolTip("Le micro écoute sur ce Mac ; rien n’est envoyé à Gemini avant le mot d’éveil. "
                                       "Retour en veille après un silence. Remplace le maintien pour parler.")
            self.wake_check.setChecked(controller.wake_enabled)
            self.wake_check.setEnabled(not controller.demo)
            self.wake_check.toggled.connect(shell.set_wake_word)
            controller.changed.connect(lambda: self.wake_check.setChecked(controller.wake_enabled))
            voice.addWidget(self.wake_check)
            voice.addWidget(label("Sans mot d’éveil, Gemini Live écoute uniquement après activation.", "subtitle"))
            voice.addWidget(button("Voix des avatars…", shell.show_voices))

            audio = section("AUDIO", settings_layout)
            sounds = QCheckBox("Sons discrets à l’activation et au changement du micro")
            sounds.setChecked(controller.sounds_enabled)
            sounds.toggled.connect(self.set_sounds)
            audio.addWidget(sounds)
            audio.addWidget(label('PÉRIPHÉRIQUES ET TESTS LOCAUX', 'eyebrow'))
            self.audio_settings = AudioSettings(controller)
            audio.addWidget(self.audio_settings)

            keys = section("RACCOURCIS", settings_layout)
            self.hotkey_check = QCheckBox('Activer le raccourci global ⌘⇧Espace')
            self.hotkey_check.setChecked(controller.hotkey_enabled)
            self.hotkey_check.setEnabled(not controller.demo)
            self.hotkey_check.toggled.connect(shell.set_global_hotkey)
            keys.addWidget(self.hotkey_check)
            self.hotkey_status = label(controller.hotkey_message, 'subtitle')
            keys.addWidget(self.hotkey_status)
            self.hotkey_retry = button('Réessayer le raccourci', shell.retry_hotkey)
            keys.addWidget(self.hotkey_retry)
            def render_hotkey():
                self.hotkey_status.setText(controller.hotkey_message)
                self.hotkey_retry.setEnabled(controller.hotkey_enabled and not controller.hotkey_active and not controller.demo)
            controller.changed.connect(render_hotkey)
            keys.addWidget(button("Palette de commandes · ⌘K", lambda: shell.experience.palette()))

            look = section("COMPAGNON ET APPARENCE", settings_layout)
            reduce = QCheckBox("Réduire les animations")
            reduce.setChecked(controller.reduced_motion)
            reduce.toggled.connect(self.set_reduced_motion)
            look.addWidget(reduce)
            look.addWidget(button("Apparence de Jarvis…", shell.show_appearances))
            look.addWidget(button("Jarvis au quotidien…", lambda: shell.experience.open()))
            look.addWidget(button("Configurer les routines vocales…", shell.show_routines))

            privacy = section("CONFIDENTIALITÉ", settings_layout)
            privacy.addWidget(label("Cette interface n’affiche et n’enregistre aucun texte de transcription."))
            self.privacy_more = button("En savoir plus ▸", self.toggle_privacy_details)
            self.privacy_more.setObjectName("quiet")
            self.privacy_more.setAccessibleName("Afficher ou masquer les explications sur l’écoute et la confidentialité")
            privacy.addWidget(self.privacy_more)
            self.privacy_details = QWidget()
            details = QVBoxLayout(self.privacy_details)
            details.setContentsMargins(0, 4, 0, 0)
            details.setSpacing(10)
            for title, body in (
                    ("VOTRE VOIX, VOTRE COMMANDE",
                     "Gemini Live écoute uniquement après activation. Les confirmations des outils restent vocales."),
                    ("ÉCOUTE ET RÉPONSE",
                     "L’écoute est suspendue pendant la lecture de la voix de Jarvis pour éviter qu’il se réponde à lui-même. Appuyez sur Échap ou cliquez sur Interrompre pour reprendre la parole."),
                    ("SESSION ET OUTILS",
                     "La session Gemini utilise le contexte de votre conversation ; les outils gardent leurs règles existantes de mémoire et de journalisation.")):
                details.addWidget(label(title, "eyebrow"))
                details.addWidget(label(body, "subtitle"))
            self.privacy_details.hide()
            privacy.addWidget(self.privacy_details)
            settings_layout.addStretch()
            settings_scroll = QScrollArea()
            settings_scroll.setWidgetResizable(True)
            settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            settings_scroll.setWidget(settings)
            self.pages.addWidget(settings_scroll)
            self.navigate(0)
        workspace.addWidget(self.pages, 1)
        row.addLayout(workspace, 1)
        self.shortcut = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
        self.shortcut.activated.connect(shell.show_compact)
        # Voice shortcuts follow the dock buttons: they only fire while those are usable.
        self.interrupt_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.interrupt_shortcut.activated.connect(controller.interrupt_voice)
        self.mic_shortcut = QShortcut(QKeySequence(Qt.Key.Key_M), self)
        self.mic_shortcut.activated.connect(controller.toggle_microphone)
        self.page_shortcuts = []
        if not compact:
            for index in range(len(self.nav)):
                shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
                shortcut.activated.connect(lambda index=index: self.navigate(index))
                self.page_shortcuts.append(shortcut)
        controller.changed.connect(self.render_shortcuts)
        self.render_shortcuts()
        if not compact:
            controller.changed.connect(self.render_nav)
            self.render_nav()

    def render_nav(self):
        """Counter of result cards not yet looked at, and a live dot while a mission or tool runs."""
        c = self.controller
        current = {(kind, card.get('time'), card.get('title')) for kind, card in c.cards.items()}
        if self.pages.currentIndex() == 1 and self.isVisible():
            self.seen_cards = current
        self.seen_cards &= current
        unseen = len(current - self.seen_cards)
        busy = (any(m['status'] in {'running', 'cancelling'} for m in c.mission_list())
                or any(entry['status'] == 'running' for entry in c.activity.values()))
        motion = not c.reduced_motion
        self.nav[1].set_signal(badge=unseen, motion=motion)
        self.nav[1].setAccessibleName('Cartes' + (f' · {unseen} nouvelle' + ('s' if unseen > 1 else '') if unseen else ''))
        self.nav[2].set_signal(live=busy, motion=motion)
        self.nav[2].setAccessibleName('Activité' + (' · en cours' if busy else ''))

    def render_shortcuts(self):
        c = self.controller
        usable = c.voice_worker is not None and c.voice_state not in {"starting", "stopping", "error"}
        self.interrupt_shortcut.setEnabled(usable)
        self.mic_shortcut.setEnabled(usable and not c.ptt_enabled)

    def navigate(self, index):
        self.shell.finish_transfer()
        self.pages.setCurrentIndex(index)
        for i, widget in enumerate(self.nav):
            widget.setChecked(index == i)
        self.page_title.setText(self.nav[index].text().upper())
        if hasattr(self, 'seen_cards') and hasattr(self, 'mic_shortcut'):
            self.render_nav()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'seen_cards') and hasattr(self, 'mic_shortcut'):
            self.render_nav()  # cards under the user's eyes again count as seen

    def toggle_privacy_details(self):
        shown = self.privacy_details.isHidden()
        self.privacy_details.setVisible(shown)
        self.privacy_more.setText("Masquer les explications ▾" if shown else "En savoir plus ▸")

    def set_reduced_motion(self, checked):
        if checked:
            self.controller.dance.stop()
        self.controller.reduced_motion = checked
        self.shell.settings.setValue("appearance/reduced_motion", checked)
        self.controller.changed.emit()

    def set_sounds(self, checked):
        self.controller.set_sounds(checked)
        self.shell.settings.setValue("audio/sounds", checked)

    def closeEvent(self, event):
        if self.compact:
            self.shell.remember_companion()
        self.shell.finish_transfer()
        event.ignore()
        if self.shell.has_tray:
            self.hide()
        else:
            self.shell.quit()
