"""python -m jarvis.schedule status (idea 28)."""
from contextlib import redirect_stdout
from io import StringIO

import pytest

from jarvis.schedule.__main__ import cmd_status, main, schedule_status
from jarvis.schedule.agent import agent_plist_path
from jarvis.schedule.reminders import ReminderStore
from jarvis.schedule.store import ScheduledMessageStore


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SCHEDULE_PATH", str(tmp_path / "scheduled.db"))
    monkeypatch.setenv("JARVIS_REMINDERS_PATH", str(tmp_path / "reminders.db"))
    return ScheduledMessageStore(), ReminderStore()


def run(**kwargs):
    out = StringIO()
    with redirect_stdout(out):
        code = cmd_status(**kwargs)
    return code, out.getvalue()


def test_missing_agent_is_reported_with_the_fix(stores, tmp_path):
    code, text = run(now=10_000, home=tmp_path, platform="darwin")
    assert code == 1
    assert "ABSENT" in text and "launchctl bootstrap" in text


def test_installed_agent_with_late_items_points_to_the_log(stores, tmp_path):
    messages, reminders = stores
    plist = agent_plist_path(tmp_path)
    plist.parent.mkdir(parents=True)
    plist.write_text("<plist/>")
    reminders.add("Appeler", 10_000 - 3600)
    messages.add("WhatsApp", "Marie", "Coucou", 10_000 - 7200)
    status = schedule_status(now=10_000, home=tmp_path, platform="darwin")
    assert status["agent"] == "installed"
    assert status["late_messages"] == 1 and status["late_reminders"] == 1
    code, text = run(now=10_000, home=tmp_path, platform="darwin")
    assert code == 1 and "scheduler.log" in text


def test_healthy_status_and_last_delivery(stores, tmp_path):
    messages, reminders = stores
    plist = agent_plist_path(tmp_path)
    plist.parent.mkdir(parents=True)
    plist.write_text("<plist/>")
    row = reminders.add("Futur", 99_999_999_999)
    status = schedule_status(now=10_000, home=tmp_path, platform="darwin")
    assert status["late_reminders"] == 0 and status["last_reminder_delivered"] is None
    code, text = run(now=10_000, home=tmp_path, platform="darwin")
    assert code == 0 and "installe" in text and "jamais" in text
    assert row["id"]


def test_install_uses_bootstrap_and_status_subcommand_exists(stores):
    out = StringIO()
    with redirect_stdout(out):
        assert main(["install"]) == 0
    text = out.getvalue()
    assert "launchctl bootstrap gui/$(id -u)" in text and "launchctl bootout" in text
    with redirect_stdout(StringIO()):
        assert main(["status"]) in (0, 1)
