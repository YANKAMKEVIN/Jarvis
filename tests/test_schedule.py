import asyncio
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jarvis.schedule.__main__ import main as schedule_main

from jarvis.capabilities.results import ToolResult
from jarvis.live.registry import create_live_registry
from jarvis.schedule.runner import DEFAULT_GRACE_SECONDS, deliver_due
from jarvis.schedule.store import (
    ScheduleError,
    ScheduledMessageStore,
    parse_due_at,
)


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


class RecurrenceTests(unittest.TestCase):
    def test_add_stores_recurrence(self):
        store = make_store(Clock())
        row = store.add("WhatsApp", "A", "x", due_at=2000.0, recurrence="daily")
        self.assertEqual(row["recurrence"], "daily")

    def test_invalid_recurrence_rejected(self):
        with self.assertRaises(ScheduleError):
            make_store(Clock()).add("WhatsApp", "A", "x", due_at=2000.0, recurrence="hourly")

    def test_successful_daily_send_arms_next_occurrence(self):
        store = make_store(Clock(now=2000.0))
        store.add("WhatsApp", "Marie", "coucou", due_at=1900.0, recurrence="daily")
        messaging = FakeMessaging()

        deliver_due(store, messaging, screen_unlocked=lambda: True, now=2000.0)

        # Original marked sent, a new pending occurrence armed one day later.
        pending = store.list("pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["recurrence"], "daily")
        self.assertEqual(pending[0]["due_at"], 1900.0 + 86400.0)

    def test_recurrence_catches_up_past_periods(self):
        store = make_store(Clock())
        store.add("WhatsApp", "Marie", "x", due_at=1000.0, recurrence="daily")
        messaging = FakeMessaging()
        # now is 3 days after due: next occurrence must be in the future.
        now = 1000.0 + 3 * 86400.0 + 10
        deliver_due(store, messaging, screen_unlocked=lambda: True, now=now)

        nxt = store.list("pending")[0]["due_at"]
        self.assertGreater(nxt, now)

    def test_one_shot_does_not_rearm(self):
        store = make_store(Clock(now=2000.0))
        store.add("WhatsApp", "Marie", "x", due_at=1900.0, recurrence="none")
        deliver_due(store, FakeMessaging(), screen_unlocked=lambda: True, now=2000.0)
        self.assertEqual(store.list("pending"), [])


class ParseDueAtTests(unittest.TestCase):
    def test_future_iso_returns_epoch(self):
        epoch = parse_due_at("2999-01-01T09:00", now=1000.0)
        self.assertGreater(epoch, 1000.0)

    def test_past_is_rejected(self):
        with self.assertRaises(ScheduleError) as ctx:
            parse_due_at("2000-01-01T09:00", now=4_000_000_000.0)
        self.assertEqual(ctx.exception.code, "due_in_past")

    def test_garbage_is_rejected(self):
        with self.assertRaises(ScheduleError) as ctx:
            parse_due_at("demain matin", now=1000.0)
        self.assertEqual(ctx.exception.code, "invalid_when")

    def test_blank_is_rejected(self):
        with self.assertRaises(ScheduleError):
            parse_due_at("   ", now=1000.0)


class FakeMemory:
    def resolve_person(self, name):
        return None

    def log_action(self, *args, **kwargs):
        return None


class ScheduleToolsTest(unittest.TestCase):
    def _tools(self):
        tmp = tempfile.mkdtemp()
        store = ScheduledMessageStore(path=Path(tmp) / "scheduled.db")
        registry = create_live_registry(
            schedule_store=store, memory_capability=FakeMemory(),
        )
        tools = {tool.info.name: tool for tool in registry.livekit_tools()}
        return tools, store

    def test_schedule_then_confirm_stores_pending(self):
        tools, store = self._tools()
        when = (datetime.now() + timedelta(days=1)).isoformat(timespec="minutes")

        prepared = asyncio.run(tools["schedule_message"]("Marie", "Salut", when))
        self.assertTrue(prepared["ok"])
        self.assertTrue(prepared["requires_confirmation"])
        self.assertEqual(store.list("pending"), [])  # not scheduled until confirmed

        confirmed = asyncio.run(tools["confirm_action"](prepared["token"]))
        self.assertTrue(confirmed["ok"])
        pending = store.list("pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["recipient"], "Marie")
        self.assertEqual(pending[0]["text"], "Salut")

    def test_schedule_rejects_past_time(self):
        tools, store = self._tools()
        result = asyncio.run(tools["schedule_message"]("Marie", "Salut", "2000-01-01T09:00"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "due_in_past")

    def test_list_and_cancel(self):
        tools, store = self._tools()
        row = store.add("WhatsApp", "Marie", "Salut", due_at=4_000_000_000.0)

        listed = asyncio.run(tools["list_scheduled_messages"]())
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["scheduled"][0]["id"], row["id"])

        cancelled = asyncio.run(tools["cancel_scheduled_message"](row["id"]))
        self.assertTrue(cancelled["ok"])
        self.assertEqual(store.get(row["id"])["status"], "cancelled")

    def test_cancel_unknown_id(self):
        tools, store = self._tools()
        result = asyncio.run(tools["cancel_scheduled_message"](999))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "scheduled_message_not_found")


class CLITest(unittest.TestCase):
    def _env(self):
        tmp = tempfile.mkdtemp()
        return {
            "JARVIS_SCHEDULE_PATH": str(Path(tmp) / "scheduled.db"),
            "JARVIS_REMINDERS_PATH": str(Path(tmp) / "reminders.db"),
        }

    def test_install_prints_agent_without_touching_system(self):
        out = StringIO()
        with redirect_stdout(out):
            code = schedule_main(["install"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("com.jarvis.scheduler", text)
        self.assertIn("launchctl load", text)

    def test_list_empty_store(self):
        with patch.dict(os.environ, self._env(), clear=False):
            out = StringIO()
            with redirect_stdout(out):
                code = schedule_main(["list"])
        self.assertEqual(code, 0)
        self.assertIn("Aucun message", out.getvalue())

    def test_deliver_empty_store_sends_nothing(self):
        # No due rows => deliver_due never touches the GUI or the screen check.
        with patch.dict(os.environ, self._env(), clear=False), patch(
            "jarvis.schedule.__main__.macos_notifier"
        ) as notifier:
            out = StringIO()
            with redirect_stdout(out):
                code = schedule_main(["deliver"])
        notifier.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn("sent=0", out.getvalue())


if __name__ == "__main__":
    unittest.main()
