import tempfile
import unittest
from pathlib import Path

from jarvis.capabilities.results import ToolResult
from jarvis.schedule.runner import DEFAULT_GRACE_SECONDS, deliver_due
from jarvis.schedule.store import ScheduleError, ScheduledMessageStore


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeMessaging:
    def __init__(self, verify_ok=True, send_ok=True, send_error=None, verify_error=None):
        self.verify_ok = verify_ok
        self.send_ok = send_ok
        self.send_error = send_error
        self.verify_error = verify_error
        self.sent = []

    def ensure_recipient(self, app, recipient):
        if self.verify_ok:
            return ToolResult.success(action="verify_recipient", message="ok")
        return ToolResult.failure(
            action="verify_recipient", message="ko",
            error_code=self.verify_error or "recipient_not_verified",
        )

    def send_text(self, app, text):
        if self.send_ok:
            self.sent.append((app, text))
            return ToolResult.success(
                action="send_text", message="ok",
                command_executed=True, state_confirmed=True,
            )
        return ToolResult.failure(
            action="send_text", message="ko",
            error_code=self.send_error or "composer_not_filled",
        )


def make_store(clock):
    tmp = tempfile.mkdtemp()
    return ScheduledMessageStore(path=Path(tmp) / "scheduled.db", clock=clock)


class StoreTests(unittest.TestCase):
    def test_add_and_get(self):
        clock = Clock()
        store = make_store(clock)
        row = store.add("WhatsApp", "Marie", "Salut", due_at=2000.0)

        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["recipient"], "Marie")
        self.assertEqual(row["attempts"], 0)
        self.assertEqual(store.get(row["id"])["text"], "Salut")

    def test_due_returns_only_past_pending(self):
        clock = Clock(now=1500.0)
        store = make_store(clock)
        store.add("WhatsApp", "A", "x", due_at=1000.0)  # due
        future = store.add("WhatsApp", "B", "y", due_at=5000.0)  # not due

        due = store.due()
        self.assertEqual([r["recipient"] for r in due], ["A"])
        self.assertNotIn(future["id"], [r["id"] for r in due])

    def test_cancel_only_pending(self):
        clock = Clock()
        store = make_store(clock)
        row = store.add("WhatsApp", "A", "x", due_at=2000.0)

        self.assertTrue(store.cancel(row["id"]))
        self.assertEqual(store.get(row["id"])["status"], "cancelled")
        self.assertFalse(store.cancel(row["id"]))  # already cancelled

    def test_mark_sent_and_failed_and_attempt(self):
        clock = Clock()
        store = make_store(clock)
        row = store.add("WhatsApp", "A", "x", due_at=2000.0)
        store.record_attempt(row["id"], "ecran verrouille")
        self.assertEqual(store.get(row["id"])["status"], "pending")
        self.assertEqual(store.get(row["id"])["attempts"], 1)

        store.mark_sent(row["id"])
        self.assertEqual(store.get(row["id"])["status"], "sent")

    def test_validation(self):
        store = make_store(Clock())
        with self.assertRaises(ScheduleError):
            store.add("WhatsApp", "A", "   ", due_at=2000.0)
        with self.assertRaises(ScheduleError):
            store.add("", "A", "x", due_at=2000.0)
        with self.assertRaises(ScheduleError):
            store.add("WhatsApp", "A", "x", due_at="demain")


class RunnerTests(unittest.TestCase):
    def test_delivers_when_unlocked_and_verified(self):
        clock = Clock(now=2000.0)
        store = make_store(clock)
        row = store.add("WhatsApp", "Marie", "Salut", due_at=1900.0)
        messaging = FakeMessaging()
        notes = []

        results = deliver_due(
            store, messaging,
            screen_unlocked=lambda: True, now=2000.0,
            notifier=notes.append,
        )

        self.assertEqual(results["sent"], [row["id"]])
        self.assertEqual(messaging.sent, [("WhatsApp", "Salut")])
        self.assertEqual(store.get(row["id"])["status"], "sent")
        self.assertTrue(any("envoye" in n for n in notes))

    def test_locked_defers_within_grace(self):
        clock = Clock(now=2000.0)
        store = make_store(clock)
        row = store.add("WhatsApp", "Marie", "Salut", due_at=1990.0)
        messaging = FakeMessaging()

        results = deliver_due(
            store, messaging, screen_unlocked=lambda: False, now=2000.0,
        )

        self.assertEqual(results["deferred"], [(row["id"], "ecran verrouille")])
        self.assertEqual(store.get(row["id"])["status"], "pending")
        self.assertEqual(messaging.sent, [])

    def test_locked_past_grace_fails_and_notifies(self):
        store = make_store(Clock())
        row = store.add("WhatsApp", "Marie", "Salut", due_at=1000.0)
        messaging = FakeMessaging()
        notes = []

        results = deliver_due(
            store, messaging, screen_unlocked=lambda: False,
            now=1000.0 + DEFAULT_GRACE_SECONDS + 1, notifier=notes.append,
        )

        self.assertEqual(results["failed"], [(row["id"], "ecran verrouille")])
        self.assertEqual(store.get(row["id"])["status"], "failed")
        self.assertTrue(any("non envoye" in n for n in notes))

    def test_unverified_recipient_defers_then_fails(self):
        store = make_store(Clock())
        row = store.add("WhatsApp", "Marie", "Salut", due_at=1000.0)
        messaging = FakeMessaging(verify_ok=False)

        within = deliver_due(store, messaging, screen_unlocked=lambda: True, now=1000.0)
        self.assertEqual(store.get(row["id"])["status"], "pending")
        self.assertTrue(within["deferred"])

        deliver_due(
            store, messaging, screen_unlocked=lambda: True,
            now=1000.0 + DEFAULT_GRACE_SECONDS + 1,
        )
        self.assertEqual(store.get(row["id"])["status"], "failed")
        self.assertEqual(messaging.sent, [])

    def test_send_failure_is_not_marked_sent(self):
        store = make_store(Clock())
        row = store.add("WhatsApp", "Marie", "Salut", due_at=1000.0)
        messaging = FakeMessaging(send_ok=False, send_error="composer_not_filled")

        deliver_due(store, messaging, screen_unlocked=lambda: True, now=1000.0)

        self.assertEqual(store.get(row["id"])["status"], "pending")  # deferred, retry
        self.assertEqual(messaging.sent, [])


if __name__ == "__main__":
    unittest.main()
