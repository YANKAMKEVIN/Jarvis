"""Configurable global shortcuts with conflict detection (idea 45)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from jarvis.desktop.hotkey import SPACE_COMBOS, GlobalHotkey, HoldHotkey, combo_conflicts


class Backend:
    def __init__(self): self.started = 0
    def start(self, trigger, released=None):
        self.started += 1
        return True
    def close(self): return True


def test_conflicts_block_duplicates_and_warn_on_known_shortcuts():
    assert combo_conflicts("cmd_shift", "cmd_shift")[0].startswith("déjà")
    assert "Finder" in combo_conflicts("cmd_option", "cmd_shift")[0]
    assert combo_conflicts("option_shift", "cmd_shift") == []


def test_hotkeys_announce_the_chosen_combination():
    backend = Backend()
    show = GlobalHotkey(lambda: None, backend_factory=lambda: backend, platform="darwin", combo_key="ctrl_shift")
    show.set_enabled(True)
    assert show.message.startswith("⌃⇧Espace actif")
    hold = HoldHotkey(lambda: None, lambda: None, backend_factory=lambda: backend, platform="darwin", combo_key="option_shift")
    hold.set_enabled(True)
    assert hold.message == "Maintenir ⌥⇧Espace pour parler."
    assert GlobalHotkey(lambda: None, combo_key="nope").combo_key == "cmd_shift"


def test_settings_change_saves_rejects_duplicates_and_updates_messages(monkeypatch):
    from jarvis.desktop.app import Controller, DesktopShell, STYLE
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)

    class Settings:
        def __init__(self): self.values = {}
        def value(self, key, default=None): return self.values.get(key, default)
        def setValue(self, key, value): self.values[key] = value

    controller = Controller()
    settings = Settings()
    shell = DesktopShell(app, controller, settings=settings)
    try:
        boxes = shell.full.combo_boxes
        assert boxes["show"].currentData() == "cmd_shift" and boxes["hold"].currentData() == "cmd_option"
        boxes["hold"].setCurrentIndex(boxes["hold"].findData("cmd_shift"))
        assert boxes["hold"].currentData() == "cmd_option" and "Refusé" in shell.full.combo_warning.text()
        boxes["hold"].setCurrentIndex(boxes["hold"].findData("option_shift"))
        assert settings.values["input/hold_combo"] == "option_shift"
        assert shell.hold_hotkey.combo_key == "option_shift"
        assert "⌥⇧Espace" in controller.ptt_hotkey_message
        assert len(SPACE_COMBOS) == boxes["show"].count()
    finally:
        shell.finish_transfer()
        for window in (shell.full, shell.compact, shell.orb_window): window.hide()
