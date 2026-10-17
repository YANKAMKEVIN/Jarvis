import os
from pathlib import Path
import pytest
pytest.importorskip("dotenv")
from jarvis.desktop.live_runtime import prepare_environment, VoiceSetupError


def test_finder_config_preserves_explicit_env_and_loads_only_allowed_keys(monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', 'terminal-value')
    monkeypatch.delenv('JARVIS_GEMINI_LIVE_VOICE', raising=False)
    monkeypatch.delenv('JARVIS_GEMINI_LIVE_MODEL', raising=False)
    monkeypatch.delenv('UNRELATED_SETTING', raising=False)
    monkeypatch.setattr(Path, 'is_file', lambda self: True)
    def values(path, **kwargs):
        assert kwargs['interpolate'] is False
        if path.name == 'desktop.env':
            return {'GOOGLE_API_KEY': 'file-value', 'JARVIS_GEMINI_LIVE_VOICE': 'Puck', 'UNRELATED_SETTING': 'ignored'}
        return {'JARVIS_GEMINI_LIVE_VOICE': 'other', 'JARVIS_GEMINI_LIVE_MODEL': 'test-model'}
    monkeypatch.setattr('dotenv.dotenv_values', values)
    prepare_environment()
    assert os.environ['GOOGLE_API_KEY'] == 'terminal-value'
    assert os.environ['JARVIS_GEMINI_LIVE_VOICE'] == 'Puck'
    assert os.environ['JARVIS_GEMINI_LIVE_MODEL'] == 'test-model'
    assert 'UNRELATED_SETTING' not in os.environ


def test_missing_key_does_not_prompt_for_microphone(monkeypatch):
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.setattr(Path, 'is_file', lambda self: False)
    with pytest.raises(VoiceSetupError, match='Clé Gemini manquante'):
        prepare_environment()
