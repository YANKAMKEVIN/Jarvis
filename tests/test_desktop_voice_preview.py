"""No microphone API is available to these preview generation/playback fakes."""
import asyncio
from contextlib import asynccontextmanager
from threading import Event
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
import pytest
from jarvis.desktop.voice_preview import (MAX_BYTES, PREVIEW_TEXT, VoicePreview,
    collect_preview, generate_preview, play_preview)
from jarvis.desktop.voices import VOICES, VOICE_IDS
from test_desktop_voices import shell


def response(data=b'\x01\x00'*40, mime='audio/pcm;rate=24000', complete=True):
    return NS(server_content=NS(model_turn=NS(parts=[NS(inline_data=NS(data=data, mime_type=mime))]), turn_complete=complete))


class Session:
    def __init__(self, responses):
        self.responses = responses
        self.send_client_content = AsyncMock()
    async def receive(self):
        for item in self.responses:
            yield item


def test_expanded_catalog_is_unique_and_defaults_are_preserved():
    assert len(VOICES) == len(VOICE_IDS) == 30
    assert {'Puck','Kore','Charon','Aoede','Fenrir','Sulafat','Zephyr'} <= VOICE_IDS


def test_collects_fixed_text_and_complete_pcm():
    async def scenario():
        session = Session([NS(server_content=None), response(complete=False), response()])
        assert len(await collect_preview(session)) == 160
        text = session.send_client_content.call_args.kwargs['turns']['parts'][0]['text']
        assert text == PREVIEW_TEXT
    asyncio.run(scenario())


@pytest.mark.parametrize('responses', [[], [response(b'')], [response(b'1')],
    [response(mime='audio/pcm;rate=48000')], [response(mime='audio/pcm;rate=240000')],
    [response(complete=False)], [response(mime='image/png')],
    [response(b'0'*(MAX_BYTES+2))]])
def test_rejects_empty_oversized_or_unsupported_audio(responses):
    with pytest.raises(ValueError): asyncio.run(collect_preview(Session(responses)))


def test_network_config_has_no_tools_or_microphone_and_closes(monkeypatch):
    monkeypatch.setattr('jarvis.desktop.live_runtime.prepare_environment', lambda: None)
    monkeypatch.setenv('GOOGLE_API_KEY', 'fake-test-key')
    connections = []
    @asynccontextmanager
    async def connect(**kwargs):
        connections.append(kwargs)
        yield Session([response()])
    client = NS(aio=NS(live=NS(connect=connect), aclose=AsyncMock()), close=Mock())
    assert asyncio.run(generate_preview('Sulafat', Event(), lambda **kw: client))
    config = connections[0]['config']
    assert config['speech_config']['voice_config']['prebuilt_voice_config']['voice_name'] == 'Sulafat'
    assert 'tools' not in config
    client.aio.aclose.assert_awaited_once()
    client.close.assert_called_once()


def test_cancels_network_request_and_closes_client(monkeypatch):
    monkeypatch.setattr('jarvis.desktop.live_runtime.prepare_environment', lambda: None)
    monkeypatch.setenv('GOOGLE_API_KEY', 'fake-test-key')
    stopped = Event()
    @asynccontextmanager
    async def connect(**kwargs):
        await asyncio.Event().wait()
        yield
    client = NS(aio=NS(live=NS(connect=connect), aclose=AsyncMock()), close=Mock())
    async def scenario():
        task = asyncio.create_task(generate_preview('Puck', stopped, lambda **kwargs: client))
        await asyncio.sleep(.02)
        stopped.set()
        assert await asyncio.wait_for(task, 1) is None
    asyncio.run(scenario())
    client.aio.aclose.assert_awaited_once()
    client.close.assert_called_once()


def test_playback_only_opens_output_and_stop_aborts():
    stopped = Event()
    speaker = Mock()
    speaker.__enter__ = Mock(return_value=speaker)
    speaker.__exit__ = Mock(return_value=False)
    speaker.write.side_effect = lambda data: stopped.set()
    devices = NS(check_output_settings=Mock(), RawOutputStream=Mock(return_value=speaker))
    play_preview(b'0'*6000, None, stopped, devices)
    devices.RawOutputStream.assert_called_once_with(device=None, samplerate=24000, channels=1, dtype='int16')
    speaker.write.assert_called_once()
    speaker.abort.assert_called_once()


def test_worker_redacts_provider_error_without_playback(shell):
    app, c, s = shell
    async def fail(*_): raise RuntimeError('PRIVATE_PROVIDER_PAYLOAD')
    player = Mock()
    worker = VoicePreview('Puck', generator=fail, player=player)
    events = []
    worker.event.connect(events.append)
    worker.run()
    assert events[-1]['state'] == 'error'
    assert 'PRIVATE_PROVIDER_PAYLOAD' not in str(events)
    player.assert_not_called()


def test_ui_preview_ownership_blocks_voice_and_stops_on_escape(shell, monkeypatch):
    from PySide6.QtCore import QObject, Signal, Qt
    from PySide6.QtTest import QTest
    app, c, s = shell
    class Worker(QObject):
        event = Signal(object)
        finished = Signal()
        def __init__(self, voice, output_choice, parent=None):
            super().__init__(parent); self.voice = voice; self.stop = Mock()
        def start(self): pass
    monkeypatch.setattr('jarvis.desktop.voice_preview.VoicePreview', Worker)
    assert not c.start_voice_preview('Puck')  # Demo never generates or opens devices.
    c.demo = False
    s.show_voices()
    s.voice_dialog.listen.click()
    worker = c.audio_worker
    assert worker.voice == 'Puck' and c.audio_job_kind == 'voice_preview'
    assert not s.voice_dialog.listen.isEnabled() and s.voice_dialog.stop.isEnabled()
    assert not c.local_mic_open
    assert not c.start_voice_preview('Kore')
    c.start_voice()
    assert c.voice_worker is None
    s.voice_dialog.voices.setCurrentIndex(s.voice_dialog.voices.findData('Sulafat'))
    worker.stop.assert_called()
    assert c.selected_voice == 'Sulafat'
    QTest.keyClick(s.voice_dialog, Qt.Key.Key_Escape)
    worker.stop.assert_called()
    worker.finished.emit()
    assert c.audio_worker is None and c.audio_job_state == 'idle'


def test_search_and_new_voice_assignment_do_not_start_audio(shell):
    app, c, s = shell
    s.show_voices()
    dialog = s.voice_dialog
    dialog.search.setText('chaleureuse')
    assert not dialog.voices.view().isRowHidden(dialog.voices.findData('Sulafat'))
    assert dialog.voices.view().isRowHidden(dialog.voices.findData('Charon'))
    dialog.voices.setCurrentIndex(dialog.voices.findData('Sulafat'))
    assert c.selected_voice == 'Sulafat'
    assert c.audio_worker is None and c.voice_worker is None


def test_favorites_persist_without_changing_avatar_voice(shell):
    from jarvis.desktop.voices import VoicePreferences
    app, c, s = shell
    s.show_voices()
    dialog = s.voice_dialog
    dialog.voices.setCurrentIndex(dialog.voices.findData('Sulafat'))
    assigned = c.selected_voice
    dialog.favorite.click()
    assert dialog.voices.itemData(0) == 'Sulafat'
    assert VoicePreferences(s.settings).favorites() == {'Sulafat'}
    assert c.selected_voice == assigned and c.audio_worker is None
    dialog.favorite.click()
    assert not VoicePreferences(s.settings).favorites()
    assert c.selected_voice == assigned


def test_active_session_blocks_preview_without_stopping_conversation(shell):
    app, c, s = shell
    c.demo = False
    c.voice_worker = object()
    c.session_voice = 'Puck'
    existing = c.voice_worker
    c.missions['kept'] = {'id':'kept','status':'running','goal':'test'}
    s.show_voices()
    assert not s.voice_dialog.listen.isEnabled()
    assert not c.start_voice_preview('Kore')
    assert c.voice_worker is existing and c.audio_worker is None
    assert c.missions['kept']['status'] == 'running'
    c.voice_worker = None
    c.changed.emit()
    assert s.voice_dialog.listen.isEnabled()
    assert 'Arrêtez le vocal' not in s.voice_dialog.preview_status.text()


def test_quit_waits_for_preview_cleanup(shell):
    app, c, s = shell
    worker = NS(stop=Mock())
    c.audio_worker = worker
    c.audio_job_kind = 'voice_preview'
    s.app = NS(quit=Mock())
    s.quit()
    worker.stop.assert_called_once()
    s.app.quit.assert_not_called()
    assert c.quit_after_voice
    c.audio_worker = None
    c.quit_after_voice = False
