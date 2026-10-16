import asyncio
import tempfile
import unittest
from pathlib import Path

from jarvis.context_store import ContextStore
from jarvis.live.registry import create_live_registry
from jarvis.schedule.reminders import ReminderStore
from jarvis.schedule.store import ScheduledMessageStore


class FakeMemory:
    def log_action(self, *a, **k):
        return None


class ClearPersonalDataTests(unittest.TestCase):
    def _tools(self):
        tmp = Path(tempfile.mkdtemp())
        ctx = ContextStore(path=tmp / "context.db")
        sched = ScheduledMessageStore(path=tmp / "scheduled.db")
        rem = ReminderStore(path=tmp / "reminders.db")
        ctx.add("un contexte")
        sched.add("WhatsApp", "A", "x", due_at=4_000_000_000.0)
        rem.add("appeler", due_at=4_000_000_000.0)
        registry = create_live_registry(
            context_store=ctx, schedule_store=sched, reminder_store=rem,
            memory_capability=FakeMemory(),
        )
        tools = {t.info.name: t for t in registry.livekit_tools()}
        return tools, ctx, sched, rem

    def test_prepare_then_confirm_purges_all(self):
        tools, ctx, sched, rem = self._tools()
        prep = asyncio.run(tools["clear_personal_data"]("all"))
        self.assertTrue(prep["requires_confirmation"])
        # Not purged until confirmed.
        self.assertEqual(len(ctx.recent()), 1)

        confirmed = asyncio.run(tools["confirm_action"](prep["token"]))
        self.assertTrue(confirmed["ok"])
        self.assertEqual(confirmed["total_cleared"], 3)
        self.assertEqual(ctx.recent(), [])
        self.assertEqual(sched.list("pending"), [])
        self.assertEqual(rem.list("pending"), [])

    def test_scope_context_only(self):
        tools, ctx, sched, rem = self._tools()
        prep = asyncio.run(tools["clear_personal_data"]("context"))
        asyncio.run(tools["confirm_action"](prep["token"]))
        self.assertEqual(ctx.recent(), [])
        self.assertEqual(len(sched.list("pending")), 1)  # untouched

    def test_invalid_scope(self):
        tools, *_ = self._tools()
        result = asyncio.run(tools["clear_personal_data"]("everything"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_scope")


if __name__ == "__main__":
    unittest.main()
