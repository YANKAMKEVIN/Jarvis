"""Warn when the launchd agent that delivers reminders and messages is missing (idea 4)."""
import asyncio
from datetime import datetime, timedelta

from jarvis.live.registry import create_live_registry
from jarvis.schedule.agent import (
    MISSING_MESSAGE, agent_plist_path, scheduler_agent_missing, scheduler_agent_status,
)
from jarvis.schedule.reminders import ReminderStore


def test_status_follows_the_plist_on_macos_only(tmp_path):
    assert scheduler_agent_status(tmp_path, platform="linux") == "unsupported"
    assert scheduler_agent_status(tmp_path, platform="darwin") == "missing"
    assert scheduler_agent_missing(tmp_path, platform="darwin") is True
    plist = agent_plist_path(tmp_path)
    plist.parent.mkdir(parents=True)
    plist.write_text("<plist/>")
    assert scheduler_agent_status(tmp_path, platform="darwin") == "installed"
    assert plist.name == "com.jarvis.scheduler.plist"


class FakeMemory:
    def resolve_person(self, name, app_name=None):
        return None

    def log_action(self, *args, **kwargs):
        return None


def set_reminder(tmp_path, missing):
    registry = create_live_registry(
        reminder_store=ReminderStore(path=tmp_path / "reminders.db"),
        memory_capability=FakeMemory(), scheduler_agent_missing=lambda: missing,
    )
    tools = {t.info.name: t for t in registry.livekit_tools()}
    when = (datetime.now() + timedelta(hours=2)).isoformat(timespec="minutes")
    return asyncio.run(tools["set_reminder"]("Appeler maman", when))


def test_reminder_result_warns_when_agent_is_missing(tmp_path):
    result = set_reminder(tmp_path, True)
    assert result["ok"] is True
    assert result["scheduler_agent_missing"] is True
    assert result["warning"] == MISSING_MESSAGE
    assert "python -m jarvis.schedule install" in result["warning"]


def test_reminder_result_is_unchanged_when_agent_is_installed(tmp_path):
    result = set_reminder(tmp_path, False)
    assert result["ok"] is True
    assert "scheduler_agent_missing" not in result and "warning" not in result


def test_a_failing_check_never_breaks_the_tool(tmp_path):
    def broken():
        raise OSError("no home")
    registry = create_live_registry(
        reminder_store=ReminderStore(path=tmp_path / "r.db"), memory_capability=FakeMemory(),
        scheduler_agent_missing=broken,
    )
    assert registry._scheduler_agent_warning() == {}


def test_dashboard_offers_installation_when_agent_is_missing():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel
    from jarvis.desktop.dashboard import make_jarvis_dashboard
    QApplication.instance() or QApplication([])
    with_warning = make_jarvis_dashboard([], [], {"scheduler_missing": 1})
    texts = " ".join(w.text() for w in with_warning.findChildren(QLabel))
    assert "Agent d'envoi absent" in texts and "python -m jarvis.schedule install" in texts
    without = make_jarvis_dashboard([], [], {})
    assert "Agent d'envoi absent" not in " ".join(w.text() for w in without.findChildren(QLabel))
