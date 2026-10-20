"""Avatar-first transparent compact window, with two hover/keyboard controls."""
from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMenu, QPushButton
from jarvis.desktop.orb_window import InteractiveOrb, OrbWindow
from jarvis.desktop.tray import presence


class CompanionAvatar(InteractiveOrb):
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.press is not None:
            self.press = None
            self.window_owner.shell.remember_companion()
            event.accept()  # Clicking the avatar never starts voice or opens a window.
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.window_owner.reveal_controls(keyboard=True)
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.window_owner.conceal_controls()
            event.accept()
        else:
            super().keyPressEvent(event)


class CompanionWindow(OrbWindow):
    avatar_class = CompanionAvatar
    avatar_size = 320

    def __init__(self, controller, shell):
        super().__init__(controller, shell)
        self.setWindowTitle('Jarvis · Compagnon')
        self.orb.pedestal = False
        self.setFixedSize(320, 340)
        self.layout().setContentsMargins(0, 20, 0, 0)
        self.layout().removeWidget(self.status)
        self.status.hide()
        self.hovered = self.keyboard_controls = self.menu_open = False
        self.menu = None
        self.open_button = self.control('↗', 'Ouvrir Jarvis et les missions', shell.show_full, 242)
        self.menu_button = self.control('•••', 'Commandes du compagnon', self.open_menu, 280)
        self.orb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.orb.setAccessibleName('Compagnon Jarvis · faire glisser pour déplacer · Entrée pour les commandes')
        for widget in (self, self.orb, self.open_button, self.menu_button):
            widget.installEventFilter(self)
        self.render()

    def control(self, text, name, callback, x):
        button = QPushButton(text, self)
        button.setAccessibleName(name)
        button.setToolTip(name)
        button.setFixedSize(32, 32)
        button.move(x, 4)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.setStyleSheet('QPushButton { background: rgba(13, 29, 43, 230); color: #d9f1ff; border: 1px solid #42617a; border-radius: 16px; padding: 0; font-size: 17px; } QPushButton:hover, QPushButton:focus { background: #29485f; border-color: #8bdcff; }')
        button.clicked.connect(callback)
        button.hide()
        return button

    def reveal_controls(self, keyboard=False):
        self.keyboard_controls = self.keyboard_controls or keyboard
        self.refresh_controls()
        if keyboard:
            self.open_button.setFocus(Qt.FocusReason.TabFocusReason)

    def conceal_controls(self):
        self.keyboard_controls = False
        self.hovered = False
        if hasattr(self, 'open_button'):
            self.open_button.clearFocus()
            self.menu_button.clearFocus()
            self.refresh_controls()

    def refresh_controls(self):
        visible = self.hovered or self.keyboard_controls or self.menu_open
        for button in (self.open_button, self.menu_button):
            button.setVisible(visible)
            button.raise_()

    def enterEvent(self, event):
        if hasattr(self, 'open_button'):
            self.hovered = True
            self.refresh_controls()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        if hasattr(self, 'open_button'):
            self.refresh_controls()
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.conceal_controls()
                return True
            if event.key() in {Qt.Key.Key_Tab, Qt.Key.Key_Backtab} and not self.keyboard_controls:
                self.reveal_controls(keyboard=True)
                return True
        if event.type() == QEvent.Type.FocusIn and event.reason() in {Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason}:
            self.keyboard_controls = True
            self.refresh_controls()
        if event.type() == QEvent.Type.FocusOut:
            QTimer.singleShot(0, self.check_focus)
        return super().eventFilter(watched, event)

    def check_focus(self):
        focus = QApplication.focusWidget()
        if focus not in (self.orb, self.open_button, self.menu_button):
            self.keyboard_controls = False
            self.refresh_controls()

    def showEvent(self, event):
        self.conceal_controls()
        super().showEvent(event)

    def hideEvent(self, event):
        if self.menu is not None:
            self.menu.close()
        self.conceal_controls()
        super().hideEvent(event)

    def render(self):
        super().render()
        status, _, _ = presence(self.controller)
        notice = self.controller.voice_error or self.controller.tool_notice
        count = len(self.controller.focus_missions())
        text = status + (f' · {count} mission(s)' if count else '')
        if notice:
            text += '\n' + notice
        self.orb.setToolTip(text + '\nGlisser pour déplacer · survoler pour les commandes')
        self.setToolTip(text)
        if getattr(self, 'menu', None) is not None:
            self.update_menu(self.menu)

    def make_menu(self):
        menu = QMenu(self)
        menu.actions_by_id = {}
        def action(key, text, callback=None):
            item = menu.addAction(text)
            item.setObjectName(key)
            if callback:
                item.triggered.connect(callback)
            menu.actions_by_id[key] = item
            return item
        action('status', '').setEnabled(False)
        action('notice', '').setEnabled(False)
        menu.addSeparator()
        action('session', '', lambda: self.controller.stop_voice() if self.controller.voice_worker else self.controller.start_voice())
        action('microphone', '', self.controller.toggle_microphone)
        action('interrupt', 'Interrompre la réponse', self.controller.interrupt_voice)
        action('stop_test', 'Arrêter le test audio local', self.controller.stop_audio_job)
        menu.addSeparator()
        action('missions', 'Voir les missions', self.shell.show_mission_details)
        action('details', 'Cartes et activité', self.shell.show_details)
        action('appearance', 'Choisir une apparence…', self.shell.show_appearances)
        action('settings', 'Réglages', self.shell.show_settings)
        menu.addSeparator()
        action('hide', 'Masquer le compagnon', self.hide)
        action('quit', 'Quitter Jarvis', self.shell.quit)
        self.update_menu(menu)
        return menu

    def update_menu(self, menu):
        c, actions = self.controller, menu.actions_by_id
        active = c.voice_worker is not None
        status, _, _ = presence(c)
        actions['status'].setText(status)
        notice = c.voice_error or c.tool_notice
        actions['notice'].setText(notice)
        actions['notice'].setVisible(bool(notice))
        actions['session'].setText('Fermeture…' if active and c.voice_state == 'error' else 'Arrêter le vocal' if active else 'Reconnecter' if c.can_reconnect else 'Démarrer Jarvis')
        actions['session'].setEnabled(not c.demo and c.audio_worker is None and c.voice_state not in {'starting','stopping'} and not (active and c.voice_state == 'error'))
        actions['microphone'].setText('Couper le micro' if c.voice_mic_open else 'Réactiver le micro')
        for key in ('microphone','interrupt'):
            actions[key].setVisible(active)
            actions[key].setEnabled(active and c.voice_state not in {'starting','stopping','error'} and not c.demo)
        actions['stop_test'].setVisible(c.audio_worker is not None)
        count = len(c.focus_missions())
        actions['missions'].setText(f'Voir les missions ({count})' if count else 'Voir les missions')

    def open_menu(self, position=None):
        if self.menu is not None:
            self.menu.close()
            self.menu.deleteLater()
        self.menu = self.make_menu()
        self.menu_open = True
        self.refresh_controls()
        self.menu.aboutToHide.connect(self.menu_closed)
        self.menu.popup(position or self.menu_button.mapToGlobal(QPoint(0, self.menu_button.height())))

    def menu_closed(self):
        self.menu_open = False
        self.hovered = self.underMouse()
        self.check_focus()
        self.refresh_controls()

    def contextMenuEvent(self, event):
        self.open_menu(event.globalPos())

    def closeEvent(self, event):
        self.shell.remember_companion()
        self.shell.finish_transfer()
        event.ignore()
        if self.shell.has_tray:
            self.hide()
        else:
            self.shell.quit()
