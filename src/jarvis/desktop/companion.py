"""Avatar-first transparent compact window, with two hover/keyboard controls."""
from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMenu, QPushButton
from jarvis.desktop.orb_window import InteractiveOrb, OrbWindow
from jarvis.desktop.tray import presence
from jarvis.desktop.companion_preferences import CompanionPreferences
from jarvis.desktop.notice_bubble import NoticeBubble


class CompanionAvatar(InteractiveOrb):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window_owner.controller.dance.stop()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.press is not None:
            self.press = None
            if self.dragged:
                self.window_owner.set_preference('anchor','free')
            self.window_owner.shell.remember_companion()
            event.accept()  # Clicking the avatar never starts voice or opens a window.
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.window_owner.controller.ptt_enabled and event.key()==Qt.Key.Key_Space:
            if not event.isAutoRepeat():
                self.local_ptt=True;self.window_owner.controller.begin_push_to_talk()
            event.accept();return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.window_owner.reveal_controls(keyboard=True)
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.window_owner.controller.dance.stop()
            self.window_owner.conceal_controls()
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key.Key_Space and getattr(self,'local_ptt',False):
            if not event.isAutoRepeat():
                self.local_ptt=False;self.window_owner.controller.end_push_to_talk()
            event.accept();return
        super().keyReleaseEvent(event)

    def focusOutEvent(self,event):
        if getattr(self,'local_ptt',False):
            self.local_ptt=False;self.window_owner.controller.end_push_to_talk()
        super().focusOutEvent(event)


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
        self.open_button = self.control('▶', 'Démarrer Jarvis', controller.contextual_voice_action, 242)
        self.voice_button = self.open_button
        self.voice_button.pressed.connect(lambda:controller.begin_push_to_talk() if controller.ptt_enabled else None)
        self.voice_button.released.connect(controller.end_push_to_talk)
        self.menu_button = self.control('•••', 'Commandes du compagnon', self.open_menu, 280)
        self.orb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.orb.setAccessibleName('Compagnon Jarvis · faire glisser pour déplacer · Entrée pour les commandes')
        for widget in (self, self.orb, self.open_button, self.menu_button):
            widget.installEventFilter(self)
        self.preferences=CompanionPreferences.load(shell.settings)
        self.discreet=False
        self.idle_timer=QTimer(self);self.idle_timer.setSingleShot(True);self.idle_timer.setInterval(180000)
        self.idle_timer.timeout.connect(self.enter_discreet)
        self.bubble=NoticeBubble(self)
        controller.notice.connect(self.bubble.enqueue)
        self.apply_preferences()
        self.render()

    def set_preference(self,key,value):
        self.controller.dance.stop()
        setattr(self.preferences,key,value)
        self.preferences.save(self.shell.settings)
        if not self.preferences.quiet: self.discreet=False
        self.apply_preferences()
        if not self.preferences.bubbles:
            self.bubble.suspend();self.bubble.queue.pending.clear()

    def apply_preferences(self):
        size=min(180,self.preferences.size) if self.discreet else self.preferences.size
        previous_size=self.size()
        self.orb.setFixedSize(size,size)
        self.setFixedSize(size,size+20)
        self.open_button.move(size-78,4);self.menu_button.move(size-40,4)
        self.setWindowOpacity(self.preferences.opacity)
        if self.preferences.anchor=='free' and self.size()!=previous_size:
            area=self.screen().availableGeometry()
            self.move(max(area.left(),min(self.x(),area.right()-self.width()+1)),
                      max(area.top(),min(self.y(),area.bottom()-self.height()+1)))
        self.apply_anchor()
        self.reset_idle()

    def apply_anchor(self):
        if self.preferences.anchor=='free': return
        from PySide6.QtGui import QGuiApplication
        screen=QGuiApplication.screenAt(self.geometry().center()) or self.screen()
        area=screen.availableGeometry();anchor=self.preferences.anchor
        self.move(area.right()-self.width()-16 if 'right' in anchor else area.left()+16,
                  area.bottom()-self.height()-16 if 'bottom' in anchor else area.top()+16)

    def reset_idle(self):
        self.idle_timer.stop()
        if self.preferences.quiet and self.isVisible() and not self.discreet:
            self.idle_timer.start()

    def enter_discreet(self):
        c=self.controller
        busy=c.dance.active or c.voice_state in {'starting','listening','speaking','thinking'} or any(m['status'] in {'running','needs_confirmation','needs_clarification'} for m in c.focus_missions())
        if not busy and not self.hovered and not self.keyboard_controls and not self.menu_open:
            self.discreet=True;self.apply_preferences()
        else: self.reset_idle()

    def wake_companion(self):
        if self.discreet:
            self.discreet=False;self.apply_preferences()
        self.reset_idle()

    def screen_changed(self,screen):
        self.controller.dance.stop()
        previous=getattr(self,'tracked_screen',None)
        if previous is not None:
            try:previous.availableGeometryChanged.disconnect(self.apply_anchor)
            except (RuntimeError,TypeError):pass
        self.tracked_screen=screen
        if screen is not None:screen.availableGeometryChanged.connect(self.apply_anchor)
        self.apply_anchor()

    def moveEvent(self,event):
        super().moveEvent(event)
        if hasattr(self,'bubble'): self.bubble.reposition()

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
        self.wake_companion()
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
            self.wake_companion()
            self.refresh_controls()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        if hasattr(self,"idle_timer"):self.reset_idle()
        if hasattr(self, 'open_button'):
            self.refresh_controls()
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.controller.dance.stop()
                self.controller.end_push_to_talk()
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
        if hasattr(self,"preferences"):
            handle=self.windowHandle()
            if not getattr(self,'screen_tracking',False) and handle is not None:
                handle.screenChanged.connect(self.screen_changed)
                self.screen_tracking=True;self.tracked_screen=None
                self.screen_changed(handle.screen())
            self.apply_anchor();self.reset_idle();self.bubble.present_next()

    def hideEvent(self, event):
        self.controller.dance.stop()
        self.controller.end_push_to_talk()
        if hasattr(self,"idle_timer"):
            self.idle_timer.stop();self.bubble.suspend()
        if self.menu is not None:
            self.menu.close()
        self.conceal_controls()
        super().hideEvent(event)

    def render(self):
        super().render()
        dance = self.controller.dance
        origin = getattr(self, "dance_origin", None)
        if dance.active and self.isVisible():
            if self.discreet:
                self.wake_companion()
            if origin is None:
                self.dance_origin = origin = self.pos()
            from jarvis.desktop.avatar_dance import travel
            dx, dy = travel(dance.elapsed)
            target = origin + QPoint(dx, dy)
            screen = self.screen().availableGeometry()
            target.setX(max(screen.left(), min(target.x(), screen.right() - self.width() + 1)))
            target.setY(max(screen.top(), min(target.y(), screen.bottom() - self.height() + 1)))
            self.move(target)
        elif origin is not None:
            self.dance_origin = None
            screen = self.screen().availableGeometry()
            origin.setX(max(screen.left(), min(origin.x(), screen.right() - self.width() + 1)))
            origin.setY(max(screen.top(), min(origin.y(), screen.bottom() - self.height() + 1)))
            self.move(origin)
        status, _, _ = presence(self.controller)
        notice = self.controller.recovery_message or self.controller.voice_error or self.controller.tool_notice
        count = len(self.controller.focus_missions())
        text = status + (f' · {count} mission(s)' if count else '')
        if notice:
            text += '\n' + notice
        self.orb.setToolTip(text + '\nGlisser pour déplacer · survoler pour les commandes')
        self.setToolTip(text)
        if hasattr(self,'voice_button'):
            c=self.controller
            label=('Interrompre la réponse' if c.voice_state=='speaking' and c.voice_worker else
                   ('Couper le micro' if c.voice_mic_open else 'Réactiver le micro') if c.voice_worker else
                   'Reconnecter' if c.can_reconnect else 'Démarrer Jarvis')
            if c.ptt_enabled:
                registered=getattr(getattr(self.shell,'hold_hotkey',None),'active',False)
                label='Maintenir pour parler · ⌘⌥Espace' if registered else 'Maintenir ce bouton pour parler · Espace sur le compagnon'
            self.voice_button.setText('■' if c.voice_state=='speaking' else '●' if c.voice_mic_open else '▶')
            self.voice_button.setAccessibleName(label);self.voice_button.setToolTip(label)
            self.voice_button.setEnabled(not c.demo and c.audio_worker is None and c.voice_state not in {'starting','stopping'} and not(c.voice_worker and c.voice_state=='error'))
        if hasattr(self,'idle_timer'):
            if getattr(self,'last_voice_state',None)!=c.voice_state:
                self.last_voice_state=c.voice_state;self.reset_idle()
            if self.discreet and c.voice_state in {'listening','speaking','thinking','error'}:self.wake_companion()
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
        action('cancel_recovery','Annuler la reconnexion',self.controller.stop_voice)
        action('microphone', '', self.controller.toggle_microphone)
        action('interrupt', 'Interrompre la réponse', self.controller.interrupt_voice)
        action('stop_test', 'Arrêter le test audio local', self.controller.stop_audio_job)
        menu.addSeparator()
        action('open_full','Ouvrir Jarvis',self.shell.show_full)
        action('missions', 'Voir les missions', self.shell.show_mission_details)
        action('details', 'Cartes et activité', self.shell.show_details)
        action('appearance', 'Choisir une apparence…', self.shell.show_appearances)
        action('routines','Routines vocales…',self.shell.show_routines)
        action('dance', 'Faire danser', lambda: self.controller.dance.stop() if self.controller.dance.active else self.controller.dance.start())
        action('settings', 'Réglages', self.shell.show_settings)
        recovery=action('recovery','Reconnecter automatiquement après coupure');recovery.setCheckable(True);recovery.setChecked(self.shell.recovery.enabled)
        recovery.triggered.connect(self.shell.set_auto_reconnect)
        hold=action('ptt','Maintenir pour parler · ⌘⌥Espace');hold.setCheckable(True);hold.setChecked(self.controller.ptt_enabled)
        hold.triggered.connect(self.shell.set_push_to_talk)
        presentation=menu.addMenu('Personnaliser le compagnon')
        from PySide6.QtGui import QActionGroup
        def options(title,key,values):
            submenu=presentation.addMenu(title);group=QActionGroup(submenu)
            for label,value in values:
                entry=submenu.addAction(label);entry.setCheckable(True);group.addAction(entry)
                entry.setChecked(getattr(self.preferences,key)==value)
                entry.triggered.connect(lambda checked=False,k=key,v=value:self.set_preference(k,v))
        options('Taille','size',[('Petit',240),('Normal',320),('Grand',400)])
        options('Opacité','opacity',[('100 %',1.),('85 %',.85),('65 %',.65)])
        options('Position','anchor',[('Libre','free'),('En bas à droite','bottom_right'),('En bas à gauche','bottom_left'),('En haut à droite','top_right'),('En haut à gauche','top_left')])
        for key,label in [('quiet','Réduire après 3 minutes au repos'),('bubbles','Bulles de notification')]:
            entry=presentation.addAction(label);entry.setCheckable(True);entry.setChecked(getattr(self.preferences,key))
            entry.triggered.connect(lambda checked,k=key:self.set_preference(k,checked))
        menu.addSeparator()
        action('hide', 'Masquer le compagnon', self.hide)
        action('quit', 'Quitter Jarvis', self.shell.quit)
        self.update_menu(menu)
        return menu

    def update_menu(self, menu):
        c, actions = self.controller, menu.actions_by_id
        from jarvis.desktop.avatar_dance import DANCERS
        actions["dance"].setText("Arrêter la danse" if c.dance.active else "Faire danser")
        actions["dance"].setEnabled(c.dance.active or (not c.reduced_motion and c.appearance in DANCERS))
        active = c.voice_worker is not None
        status, _, _ = presence(c)
        actions['status'].setText(status)
        notice = c.recovery_message or c.voice_error or c.tool_notice
        actions['notice'].setText(notice)
        actions['notice'].setVisible(bool(notice))
        actions['session'].setText('Fermeture…' if active and c.voice_state == 'error' else 'Arrêter le vocal' if active else 'Reconnecter' if c.can_reconnect else 'Démarrer Jarvis')
        actions['session'].setEnabled(not c.demo and c.audio_worker is None and c.voice_state!='stopping' and (c.voice_state!='starting' or active) and not (active and c.voice_state=='error'))
        if active and c.voice_state=='starting':actions['session'].setText('Annuler la connexion')
        actions['cancel_recovery'].setVisible(self.shell.recovery.timer.isActive() or c.reconnecting)
        actions['recovery'].setChecked(self.shell.recovery.enabled)
        actions['ptt'].setChecked(c.ptt_enabled)
        actions['microphone'].setText('Couper le micro' if c.voice_mic_open else 'Réactiver le micro')
        for key in ('microphone','interrupt'):
            actions[key].setVisible(active and not (key=='microphone' and c.ptt_enabled))
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
