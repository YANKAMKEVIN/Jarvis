"""Settings toggles and dialogs of the desktop shell."""
from __future__ import annotations

import json


class ShellSettingsMixin:
    """Settings toggles and dialogs of the desktop shell. Mixed into DesktopShell."""

    def save_devices(self):
        self.settings.setValue('audio/input_device', json.dumps(self.controller.input_choice))
        self.settings.setValue('audio/output_device', json.dumps(self.controller.output_choice))

    def hold_hotkey_changed(self):
        self.controller.ptt_hotkey_message=self.hold_hotkey.message
        self.controller.changed.emit()

    def set_auto_reconnect(self,enabled):
        self.settings.setValue('voice/auto_reconnect',enabled)
        self.recovery.set_enabled(enabled)

    def set_push_to_talk(self,enabled):
        if enabled and self.controller.wake_enabled:
            self.set_wake_word(False)
        self.controller.set_push_to_talk(enabled)
        self.settings.setValue('input/push_to_talk',enabled)
        self.hold_hotkey.set_enabled(enabled)

    def set_dance_music(self, enabled):
        self.controller.dance_music = bool(enabled)
        self.settings.setValue('dance/music', bool(enabled))
        if not enabled and self.controller.voice_worker:
            self.controller.voice_worker.stop_dance_music()

    def set_backchannel(self, enabled):
        self.controller.backchannel = bool(enabled)
        self.settings.setValue('appearance/backchannel', bool(enabled))
        self.controller.changed.emit()

    def set_wake_word(self, enabled):
        if enabled == self.controller.wake_enabled:
            return
        if enabled and self.controller.ptt_enabled:
            self.set_push_to_talk(False)  # Two ways to open the microphone would conflict.
        self.controller.set_wake_word(enabled)
        self.settings.setValue('input/wake_word', enabled)
        c = self.controller
        if enabled and not c.voice_worker and not c.demo and c.audio_worker is None:
            c.start_voice()

    def set_global_hotkey(self, enabled):
        self.controller.hotkey_enabled = enabled
        self.settings.setValue('input/global_hotkey', enabled)
        self.hotkey.set_enabled(enabled)

    def retry_hotkey(self):
        self.hotkey.set_enabled(self.controller.hotkey_enabled)

    def hotkey_changed(self):
        self.controller.hotkey_active = self.hotkey.active
        self.controller.hotkey_message = self.hotkey.message
        for window in (self.full, self.compact, self.orb_window):
            window.shortcut.setEnabled(not self.hotkey.active)
        self.controller.changed.emit()

    def set_appearance(self, appearance):
        self.controller.dance.stop()
        self.controller.appearance = self.appearance_preference.save(appearance)
        self.controller.selected_voice = self.voice_preferences.load(self.controller.appearance)
        self.controller.appearance_changed.emit(self.controller.appearance)
        self.controller.changed.emit()

    def show_routines(self):
        from jarvis.desktop.routines import RoutineDialog
        if self.routines_dialog is not None:
            self.routines_dialog.close();self.routines_dialog.deleteLater()
        self.routines_dialog=RoutineDialog(self.controller,self.visible_window())
        self.routines_dialog.show()

    def set_avatar_voice(self, appearance, voice):
        self.voice_preferences.save(appearance, voice)
        if appearance == self.controller.appearance:
            self.controller.selected_voice = voice
        self.controller.changed.emit()

    def show_voices(self):
        from jarvis.desktop.voice_selector import VoiceSelector
        if self.voice_dialog is not None:
            self.voice_dialog.close()
            self.voice_dialog.deleteLater()
        self.voice_dialog = VoiceSelector(self, self.visible_window())
        self.voice_dialog.show()

    def show_appearances(self):
        from jarvis.desktop.avatar_selector import AvatarSelector
        if self.appearance_dialog is not None:
            self.appearance_dialog.close()
            self.appearance_dialog.deleteLater()
        self.appearance_dialog = AvatarSelector(self.controller.appearance, self.visible_window())
        self.appearance_dialog.chosen.connect(self.set_appearance)
        self.appearance_dialog.show()

    def show_settings(self):
        self.show_full()
        self.finish_transfer()
        self.full.navigate(3)

    def maybe_show_onboarding(self):
        """Show the first-run permission screen once, on a real desktop only."""
        from jarvis.desktop import onboarding

        if self.controller.demo or self.app.platformName() == "offscreen":
            return None
        if not onboarding.needs_onboarding(self.settings):
            return None
        self.onboarding = onboarding.make_onboarding_dialog(self.settings)
        self.onboarding.show()
        self.onboarding.raise_()
        return self.onboarding
