"""Reminders delivered while Jarvis was away are said at the next session (idea 29)."""
import asyncio
from types import SimpleNamespace as NS

from jarvis.desktop.live_runtime import LiveRuntime
from jarvis.schedule.missed import (
    missed_announcement, missed_reminders, read_last_session_end, record_session_end,
)
from jarvis.schedule.reminders import ReminderStore


def store_with_deliveries(tmp_path):
    clock = [1_000.0]
    store = ReminderStore(path=tmp_path / "reminders.db", clock=lambda: clock[0])
    for index, (due, done) in enumerate(((1_100, 1_100), (2_100, 2_100), (3_100, 3_100))):
        row = store.add(f"Rappel {index}", due)
        clock[0] = done
        store.mark_done(row["id"])
    store.add("Encore a venir", 9_999_999_999)
    return store


def test_only_reminders_delivered_after_the_last_session_are_missed(tmp_path):
    store = store_with_deliveries(tmp_path)
    assert missed_reminders(store, None) == []  # first run: nothing to catch up
    rows = missed_reminders(store, 2_000)
    assert [row["text"] for row in rows] == ["Rappel 1", "Rappel 2"]
    text = missed_announcement(rows)
    assert "« Rappel 1 »" in text and "« Rappel 2 »" in text and "une seule phrase" in text
    assert missed_announcement([]) is None


def test_session_end_marker_round_trip(tmp_path):
    marker = tmp_path / "last"
    assert read_last_session_end(marker) is None
    record_session_end(1234.0, marker)
    assert read_last_session_end(marker) == 1234.0


def test_runtime_queues_the_announcement_once_idle(tmp_path, monkeypatch):
    store = store_with_deliveries(tmp_path)
    marker = tmp_path / "last"
    record_session_end(2_000, marker)
    monkeypatch.setenv("JARVIS_LAST_SESSION_PATH", str(marker))
    runtime = LiveRuntime(lambda event: None, prepare=lambda: None)
    runtime.components = NS(assistant=NS(registry=NS(reminder_store=store)))
    instructions = asyncio.run(runtime._queue_missed_reminders())
    assert "Rappel 2" in instructions
    assert [item[1] for item in runtime.task_announcements] == [instructions]


def test_runtime_without_store_or_with_broken_store_says_nothing(monkeypatch, tmp_path):
    runtime = LiveRuntime(lambda event: None, prepare=lambda: None)
    runtime.components = NS(assistant=NS(registry=NS()))
    assert asyncio.run(runtime._queue_missed_reminders()) is None

    class Broken:
        def list(self, *args, **kwargs): raise OSError("disk")
    monkeypatch.setenv("JARVIS_LAST_SESSION_PATH", str(tmp_path / "m"))
    record_session_end(1, tmp_path / "m")
    runtime.components = NS(assistant=NS(registry=NS(reminder_store=Broken())))
    assert asyncio.run(runtime._queue_missed_reminders()) is None and not runtime.task_announcements
