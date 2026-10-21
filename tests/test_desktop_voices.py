"""Assignments persist separately and never replace an active voice worker."""
import asyncio
import os
from unittest.mock import Mock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller, DesktopShell
from jarvis.desktop.appearances import CATALOG
from jarvis.desktop.voices import DEFAULT_VOICES, VOICE_IDS, VoicePreferences
from jarvis.desktop.live_runtime import LiveRuntime


@pytest.fixture
def shell(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable', lambda: False)
    c = Controller(demo=True)
    s = DesktopShell(app, c, QSettings(str(tmp_path/'voices.ini'), QSettings.Format.IniFormat))
    yield app, c, s
    c.voice_worker = None
    if s.voice_dialog: s.voice_dialog.close(); s.voice_dialog.deleteLater()
    s.recovery.close(); s.hold_hotkey.close(); s.power.close(); s.finish_transfer()
    for widget in (s.full, s.compact, s.orb_window): widget.hide()
    if s.tray: s.tray.hide()


def test_all_defaults_persistence_isolation_and_corrupt_preferences(tmp_path):
    path = str(tmp_path/'voices.ini')
    settings = QSettings(path, QSettings.Format.IniFormat)
    prefs = VoicePreferences(settings)
    assert set(DEFAULT_VOICES) == {a.id for a in CATALOG}
    assert {prefs.load(a.id) for a in CATALOG} <= VOICE_IDS
    other = prefs.load('neo_guide')
    prefs.save('nova_bot', 'Aoede')
    settings.sync()
    reopened = VoicePreferences(QSettings(path, QSettings.Format.IniFormat))
    assert reopened.load('nova_bot') == 'Aoede'
    assert reopened.load('neo_guide') == other
    assert reopened.reset('nova_bot') == 'Puck'
    settings.setValue('voice/avatars/nova_bot', ['bad'])
    assert prefs.load('nova_bot') == 'Puck'
    with pytest.raises(ValueError): prefs.save('nova_bot', 'made_up')
    with pytest.raises(ValueError): prefs.save('invalid_avatar', 'Puck')


def test_dialog_assigns_inactive_avatar_without_changing_session(shell):
    app, c, s = shell
    c.voice_worker, c.session_voice = object(), 'Puck'
    existing = c.voice_worker
    c.missions['kept'] = {'id':'kept', 'status':'running', 'goal':'test'}
    s.show_voices()
    dialog = s.voice_dialog
    dialog.follow_avatar('neo_guide')
    dialog.voices.setCurrentIndex(dialog.voices.findData('Aoede'))
    assert s.voice_preferences.load('neo_guide') == 'Aoede'
    assert c.appearance == 'nova_bot' and c.selected_voice == 'Puck'
    s.set_appearance('neo_guide')
    assert c.selected_voice == 'Aoede' and c.session_voice == 'Puck'
    assert c.voice_worker is existing and c.missions['kept']['status'] == 'running'
    assert 'Prochaine connexion : Aoede' in dialog.status.text()
    dialog.reset.click()
    assert c.selected_voice == 'Kore'
    s.set_appearance('nova_bot')
    assert c.selected_voice == 'Puck'


def test_menu_opens_selector_without_microphone(shell):
    app, c, s = shell
    s.show_compact()
    s.compact.make_menu().actions_by_id['voices'].trigger()
    assert s.voice_dialog.isVisible()
    assert c.voice_worker is None and not c.voice_mic_open
    assert s.voice_dialog.avatars.count() == 16
    assert s.voice_dialog.voices.count() == 30


def test_controller_passes_selected_voice_before_start(shell, monkeypatch):
    app, c, s = shell
    calls = []
    class Worker(QObject):
        event = Signal(object)
        finished = Signal()
        def set_voice(self, voice): calls.append(('voice', voice))
        def start(self): calls.append(('start',))
    monkeypatch.setattr('jarvis.desktop.live_runtime.preload_live_plugins', lambda: None)
    monkeypatch.setattr('jarvis.desktop.live_worker.LiveWorker', Worker)
    s.set_appearance('neo_guide')
    c.demo = False
    c.start_voice()
    assert calls == [('voice','Kore'), ('start',)]
    assert c.session_voice == 'Kore'
    s.set_avatar_voice('neo_guide', 'Aoede')
    assert calls == [('voice','Kore'), ('start',)]
    assert c.session_voice == 'Kore' and c.selected_voice == 'Aoede'


def test_runtime_forwards_voice_after_environment_preparation():
    async def scenario():
        from test_desktop_live_runtime import components, until
        chosen = []
        c = components()
        runtime = LiveRuntime(lambda event: None,
            factory=lambda **kwargs: chosen.append(kwargs) or c, prepare=lambda: None)
        runtime.set_voice('Aoede')
        task = asyncio.create_task(runtime.run())
        await until(lambda: runtime.ready)
        assert chosen == [{'voice':'Aoede'}]
        with pytest.raises(RuntimeError): runtime.set_voice('Puck')
        runtime.stop()
        await asyncio.wait_for(task, 1)
        with pytest.raises(ValueError): runtime.set_voice('made_up')
    asyncio.run(scenario())


def test_component_factory_passes_voice_to_model_without_mutating_environment(monkeypatch):
    from jarvis.desktop.live_runtime import create_components
    import livekit.agents
    import jarvis.live.factory as factory
    from jarvis.live.config import LiveConfig
    original = LiveConfig('test-model', 'Fenrir', .8, 'test')
    monkeypatch.setattr('jarvis.live.config.get_live_config', lambda: original)
    monkeypatch.setattr('jarvis.desktop.live_audio.LocalAudio', lambda loop: object())
    monkeypatch.setattr(factory, 'create_assistant_class', lambda agent: lambda: object())
    model_factory = Mock(return_value=object())
    monkeypatch.setattr(factory, 'create_realtime_model', model_factory)
    monkeypatch.setattr(livekit.agents, 'AgentSession', lambda **kwargs: object())
    async def scenario():
        create_components(voice='Kore')
        assert model_factory.call_args.args[1].voice == 'Kore'
        assert original.voice == 'Fenrir'
        create_components()
        assert model_factory.call_args.args[1].voice == 'Fenrir'
    asyncio.run(scenario())
