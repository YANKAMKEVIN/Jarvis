"""Malformed environment values fall back instead of crashing (idea 13)."""
import pytest

from jarvis.capabilities.diagnostics import _live_settings
from jarvis.live.config import DEFAULT_GEMINI_LIVE_TEMPERATURE, get_live_config, live_config_warnings


@pytest.mark.parametrize("raw,expected", [("0.5", 0.5), ("0,8", 0.8), (" 1 ", 1.0), ("2", 2.0), ("", DEFAULT_GEMINI_LIVE_TEMPERATURE)])
def test_valid_temperatures(monkeypatch, raw, expected):
    monkeypatch.setenv("JARVIS_GEMINI_LIVE_TEMPERATURE", raw)
    assert get_live_config().temperature == expected
    assert live_config_warnings() == []


@pytest.mark.parametrize("raw", ["chaud", "3", "-0.1", "nan", "0,8,1"])
def test_invalid_temperature_falls_back_and_is_reported(monkeypatch, raw):
    monkeypatch.setenv("JARVIS_GEMINI_LIVE_TEMPERATURE", raw)
    assert get_live_config().temperature == DEFAULT_GEMINI_LIVE_TEMPERATURE
    warnings = live_config_warnings()
    assert len(warnings) == 1 and "JARVIS_GEMINI_LIVE_TEMPERATURE" in warnings[0]
    ok, detail = _live_settings()
    assert not ok and "entre 0 et 2" in detail


def test_settings_check_passes_by_default(monkeypatch):
    monkeypatch.delenv("JARVIS_GEMINI_LIVE_TEMPERATURE", raising=False)
    assert _live_settings() == (True, "reglages valides")


def test_searxng_timeout_never_crashes_import(monkeypatch):
    from jarvis.config import _timeout_seconds
    monkeypatch.setenv("SEARXNG_TIMEOUT_SECONDS", "cinq")
    assert _timeout_seconds("SEARXNG_TIMEOUT_SECONDS", 5.0) == 5.0
    monkeypatch.setenv("SEARXNG_TIMEOUT_SECONDS", "2,5")
    assert _timeout_seconds("SEARXNG_TIMEOUT_SECONDS", 5.0) == 2.5
    monkeypatch.setenv("SEARXNG_TIMEOUT_SECONDS", "0")
    assert _timeout_seconds("SEARXNG_TIMEOUT_SECONDS", 5.0) == 5.0
