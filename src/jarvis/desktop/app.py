"""Voice-first desktop companion with explicit, guarded command-palette actions."""
from __future__ import annotations

import signal
import threading
import json
from collections import OrderedDict
from datetime import datetime
from importlib.resources import files as _resource_files

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QCheckBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QGraphicsOpacityEffect, QPushButton, QScrollArea, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from jarvis.desktop.audio_settings import AudioSettings
from jarvis.desktop.devices import valid_choice
from jarvis.desktop.hotkey import GlobalHotkey
from jarvis.desktop.tray import TrayControls
from jarvis.desktop.visuals import Orb, state_tint
from jarvis.desktop.panels import DetailPanel
from jarvis.desktop.mission_panel import MissionDeck
from jarvis.desktop.orb_window import OrbWindow
from jarvis.desktop.companion import CompanionWindow
from jarvis.desktop.presentation import STATUS_TEXT, count_label, shorten
from jarvis.desktop.surfaces import ControlDock, DragHandle, GlassSurface, NavButton, OrbTransfer
from jarvis.desktop.app_widgets import (  # noqa: F401 -- re-exported
    label,
    button,
    card,
    section,
    PeekCard,
    STYLE,
)
from jarvis.desktop.app_controller import (  # noqa: F401 -- re-exported
    Controller,
)
from jarvis.desktop.app_voice_panel import (  # noqa: F401 -- re-exported
    VoicePanel,
)
from jarvis.desktop.app_window import (  # noqa: F401 -- re-exported
    DesktopWindow,
)
from jarvis.desktop.app_shell_settings import ShellSettingsMixin
from jarvis.desktop.app_shell_views import ShellViewsMixin


class InsightRelay(QObject):
    """Carries insights from the monitor's worker thread to the GUI thread."""
    fired = Signal(object)


class DesktopShell(
    ShellSettingsMixin,
    ShellViewsMixin,
):
    def __init__(self, app, controller, settings=None):
        self.app, self.controller = app, controller
        self.settings = settings if settings is not None else QSettings("Jarvis", "Desktop")
        controller.hotkey_enabled = self.settings.value('input/global_hotkey', True) in (True, 'true')
        for key, attribute in (('audio/input_device', 'input_choice'), ('audio/output_device', 'output_choice')):
            raw = self.settings.value(key)
            if raw is not None:
                try:
                    choice = json.loads(raw) if isinstance(raw, str) else raw
                    if choice is not None and not valid_choice(choice):
                        raise ValueError('Invalid device preference')
                    setattr(controller, attribute, choice)
                except (TypeError, ValueError):
                    controller.device_config_invalid = True
        controller.ptt_enabled=self.settings.value('input/push_to_talk',False) in (True,'true')
        controller.wake_enabled = (not controller.ptt_enabled and
                                   self.settings.value('input/wake_word', False) in (True, 'true'))
        controller.devices_changed.connect(self.save_devices)
        controller.sounds_enabled = self.settings.value("audio/sounds", False) in (True, "true")
        controller.dance_music = self.settings.value("dance/music", True) in (True, "true")
        controller.backchannel = self.settings.value("appearance/backchannel", True) in (True, "true")
        controller.reduced_motion = self.settings.value("appearance/reduced_motion", controller.reduced_motion) in (True, "true")
        from jarvis.desktop.appearances import AppearancePreference
        self.appearance_preference = AppearancePreference(self.settings)
        controller.appearance = self.appearance_preference.load()
        from jarvis.desktop.voices import VoicePreferences
        self.voice_preferences = VoicePreferences(self.settings)
        controller.selected_voice = self.voice_preferences.load(controller.appearance)
        self.voice_dialog = None
        controller.appearance_requested.connect(self.show_appearances)
        self.appearance_dialog = None
        self.routines_dialog = None
        self.position_restored = False
        self.orb_position_restored = False
        self.transfer = None
        controller.changed.connect(self.motion_changed)
        self.has_tray = QSystemTrayIcon.isSystemTrayAvailable()
        controller.exit_ready.connect(app.quit)
        self.full = DesktopWindow(controller, self)
        self.compact = CompanionWindow(controller, self)
        self.orb_window = OrbWindow(controller, self)
        controller.details_requested.connect(self.show_details)
        controller.mission_details_requested.connect(self.show_mission_details)
        self.tray = None
        self.tray_controls = None
        if self.has_tray:
            self.tray = QSystemTrayIcon(app)
            self.tray_controls = TrayControls(self, self.tray)
            self.tray.show()
        app.setQuitOnLastWindowClosed(False)
        self.hotkey = GlobalHotkey(self.show_compact, parent=controller,
                                   demo=controller.demo or app.platformName() == 'offscreen')
        self.hotkey.changed.connect(self.hotkey_changed)
        self.hotkey.set_enabled(controller.hotkey_enabled)
        app.aboutToQuit.connect(self.hotkey.close)
        from jarvis.desktop.hotkey import HoldHotkey
        self.hold_hotkey=HoldHotkey(controller.begin_push_to_talk,controller.end_push_to_talk,parent=controller,
                                   demo=controller.demo or app.platformName()=='offscreen')
        self.hold_hotkey.changed.connect(self.hold_hotkey_changed)
        self.hold_hotkey.set_enabled(controller.ptt_enabled)
        app.aboutToQuit.connect(self.hold_hotkey.close)
        from jarvis.desktop.recovery import VoiceRecovery,MacPowerMonitor
        self.recovery=VoiceRecovery(controller,self.settings.value('voice/auto_reconnect',app.platformName()!='offscreen') in (True,'true'))
        controller.recovery=self.recovery
        self.power=MacPowerMonitor(controller)
        self.power.sleeping.connect(self.recovery.before_sleep)
        self.power.waking.connect(self.recovery.after_wake)
        if not controller.demo:self.power.start()
        app.aboutToQuit.connect(self.power.close)
        app.aboutToQuit.connect(self.recovery.close)
        self.quit_guard = QuitGuard(self, app)
        if controller.wake_enabled and not controller.demo and app.platformName() != 'offscreen':
            # Opt-in standby: Gemini connects, the microphone stays local-only.
            QTimer.singleShot(0, controller.start_voice)
        app.installEventFilter(self.quit_guard)
        self.onboarding = None
        self.dashboard_window = None
        self.insights_enabled = self.settings.value('insights/enabled', True) in (True, 'true')
        self.insights_spoken = self.settings.value('insights/voice', True) in (True, 'true')
        self._start_metrics_sampler()
        self._start_insight_monitor()
        from jarvis.desktop.experience import Experience
        self.experience = Experience(self)
        controller.experience = self.experience
        self.maybe_show_onboarding()
        if not controller.demo and app.platformName() != "offscreen" and self.settings.value("experience/setup_seen", False) not in (True,"true"):
            if self.onboarding:self.onboarding.finished.connect(lambda: self.experience.setup())
            else:self.experience.setup()

    def _start_metrics_sampler(self):
        """Accrue machine-metrics history while Jarvis runs (real desktop only)."""
        self.metrics_sampler = None
        self.metrics_timer = None
        if self.controller.demo or self.app.platformName() == "offscreen":
            return
        from jarvis.metrics.sampler import MetricsSampler

        sampler = MetricsSampler()
        if not sampler.available():
            return
        self.metrics_sampler = sampler
        sampler.tick()  # one baseline reading immediately
        timer = QTimer(self.full)
        timer.setInterval(20_000)
        timer.timeout.connect(sampler.tick)
        timer.start()
        self.metrics_timer = timer
        self.app.aboutToQuit.connect(timer.stop)

    def _start_insight_monitor(self):
        """Proactive anomaly alerts, checked off the GUI thread every 5 minutes.

        Rides on the sampler's history, so it only runs where the sampler does.
        """
        self.insight_monitor = None
        self.insight_timer = None
        if self.metrics_sampler is None:
            return
        from jarvis.insights.detector import InsightDetector, InsightMonitor
        from jarvis.usage.store import UsageStore

        self.insight_relay = InsightRelay()
        self.insight_relay.fired.connect(self.show_insight)
        detector = InsightDetector(metrics=self.metrics_sampler.store, usage=UsageStore(),
                                   probe=self.metrics_sampler.probe)
        self.insight_monitor = InsightMonitor(detector, notifier=self.insight_relay.fired.emit)
        timer = QTimer(self.full)
        timer.setInterval(5 * 60_000)
        timer.timeout.connect(self.check_insights)
        timer.start()
        self.insight_timer = timer
        self.app.aboutToQuit.connect(timer.stop)

    def check_insights(self):
        if self.insight_monitor is None or not self.insights_enabled:
            return
        threading.Thread(target=self.insight_monitor.tick, name='jarvis-insights',
                         daemon=True).start()

    def set_insights_enabled(self, enabled):
        self.insights_enabled = bool(enabled)
        self.settings.setValue('insights/enabled', self.insights_enabled)

    def set_insights_spoken(self, enabled):
        self.insights_spoken = bool(enabled)
        self.settings.setValue('insights/voice', self.insights_spoken)

    def show_insight(self, insight):
        if not self.insights_enabled:
            return
        if self.insights_spoken:
            self.controller.announce(insight.message)
        if self.tray is not None:
            icon = (QSystemTrayIcon.MessageIcon.Warning if insight.severity == 'warning'
                    else QSystemTrayIcon.MessageIcon.Information)
            self.tray.showMessage(f'Jarvis · {insight.title}', insight.message, icon, 10_000)
        else:
            from jarvis.schedule.runner import macos_notifier
            macos_notifier(f'{insight.title} : {insight.message}')

    def show_dashboard(self, tab: str = "jarvis"):
        """Open the tabbed dashboard on `tab` (jarvis, usage, metrics, alerts);
        each tab loads its data asynchronously the first time it is shown."""
        from jarvis.desktop.dashboard import DashboardWindow

        if self.dashboard_window is None:
            self.dashboard_window = DashboardWindow(tab=tab)
        else:
            self.dashboard_window.show_tab(tab)
            self.dashboard_window.reload()
        self.dashboard_window.show()
        self.dashboard_window.raise_()
        self.dashboard_window.activateWindow()

    def show_usage(self):
        self.show_dashboard("usage")

    def show_metrics(self):
        self.show_dashboard("metrics")

    def quit(self):
        self.finish_transfer()
        self.remember_companion()
        self.remember_orb()
        if self.controller.audio_worker:
            self.controller.quit_after_voice = True
            self.controller.stop_audio_job()
        elif self.controller.voice_worker:
            self.controller.quit_after_voice = True
            self.controller.stop_voice()
        else:
            self.app.quit()


class QuitGuard(QObject):
    def __init__(self, shell, parent):
        super().__init__(parent)
        self.shell = shell

    def eventFilter(self, watched, event):
        c = self.shell.controller
        if event.type() == QEvent.Type.Quit and (c.voice_worker or c.audio_worker):
            self.shell.quit()
            return True
        return False


def run(demo=False, compact=False, orb=False):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Jarvis")
    app.setOrganizationName("Jarvis")
    app.setStyleSheet(STYLE)
    from jarvis.desktop.tray import app_icon
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)  # also the Dock icon on macOS, inherited by every window
    controller = Controller(demo=demo)
    shell = DesktopShell(app, controller)
    shell.show_orb() if orb else shell.show_compact() if compact else shell.show_full()
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
