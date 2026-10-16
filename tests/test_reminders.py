import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jarvis.live.registry import create_live_registry
from jarvis.schedule.reminders import (
    ReminderError,
    ReminderStore,
    deliver_reminders,
)


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def make_store(clock):
    tmp = tempfile.mkdtemp()
    return ReminderStore(path=Path(tmp) / "reminders.db", clock=clock)


class ReminderStoreTests(unittest.TestCase):
    def test_add_list_cancel(self):
        store = make_store(Clock())
        row = store.add("Sortir le gateau", due_at=2000.0)
        self.assertEqual(row["status"], "pending")
        self.assertEqual(store.list("pending")[0]["text"], "Sortir le gateau")

        self.assertTrue(store.cancel(row["id"]))
        self.assertEqual(store.get(row["id"])["status"], "cancelled")
        self.assertFalse(store.cancel(row["id"]))

    def test_due_filters_by_time(self):
        store = make_store(Clock(now=1500.0))
        store.add("maintenant", due_at=1000.0)
        store.add("plus tard", due_at=9000.0)
        self.assertEqual([r["text"] for r in store.due()], ["maintenant"])

    def test_invalid_text(self):
        with self.assertRaises(ReminderError):
            make_store(Clock()).add("   ", due_at=2000.0)

    def test_deliver_fires_and_marks_done(self):
        store = make_store(Clock(now=2000.0))
        row = store.add("appeler le dentiste", due_at=1900.0)
        notes = []

        fired = deliver_reminders(store, now=2000.0, notifier=notes.append)

        self.assertEqual(fired, [row["id"]])
        self.assertEqual(store.get(row["id"])["status"], "done")
        self.assertTrue(any("dentiste" in n for n in notes))
        # second pass fires nothing (already done)
        self.assertEqual(deliver_reminders(store, now=2000.0, notifier=notes.append), [])


class FakeMemory:
    def resolve_person(self, name):
        return None

    def log_action(self, *args, **kwargs):
        return None


class ReminderToolsTest(unittest.TestCase):
    def _tools(self):
        tmp = tempfile.mkdtemp()
        store = ReminderStore(path=Path(tmp) / "reminders.db")
        registry = create_live_registry(
            reminder_store=store, memory_capability=FakeMemory(),
        )
        return {t.info.name: t for t in registry.livekit_tools()}, store

    def test_set_reminder_stores_directly_without_confirmation(self):
        tools, store = self._tools()
        when = (datetime.now() + timedelta(hours=2)).isoformat(timespec="minutes")

        result = asyncio.run(tools["set_reminder"]("Appeler maman", when))

        self.assertTrue(result["ok"])
        self.assertNotIn("requires_confirmation", result)  # no outward action
        self.assertEqual(len(store.list("pending")), 1)

    def test_set_reminder_rejects_past(self):
        tools, store = self._tools()
        result = asyncio.run(tools["set_reminder"]("x", "2000-01-01T09:00"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "due_in_past")

    def test_list_and_cancel(self):
        tools, store = self._tools()
        row = store.add("test", due_at=4_000_000_000.0)
        listed = asyncio.run(tools["list_reminders"]())
        self.assertEqual(listed["count"], 1)

        cancelled = asyncio.run(tools["cancel_reminder"](row["id"]))
        self.assertTrue(cancelled["ok"])
        self.assertEqual(store.get(row["id"])["status"], "cancelled")

    def test_cancel_unknown(self):
        tools, store = self._tools()
        result = asyncio.run(tools["cancel_reminder"](123))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "reminder_not_found")


if __name__ == "__main__":
    unittest.main()
