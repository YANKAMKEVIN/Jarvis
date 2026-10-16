import asyncio
import tempfile
import unittest
from pathlib import Path

from jarvis.live.registry import create_live_registry
from jarvis.memory.store import MemoryStore
from jarvis.capabilities.memory import MemoryCapability
from jarvis.schedule.reminders import ReminderStore
from jarvis.schedule.store import ScheduledMessageStore


class PrivacyOverviewTest(unittest.TestCase):
    def test_counts_across_stores(self):
        tmp = Path(tempfile.mkdtemp())
        memory = MemoryCapability(MemoryStore(tmp / "memory.db"))
        schedule = ScheduledMessageStore(path=tmp / "scheduled.db")
        reminders = ReminderStore(path=tmp / "reminders.db")

        memory.remember("fact", "dentiste", "Dr Martin")
        schedule.add("WhatsApp", "Marie", "x", due_at=4_000_000_000.0)
        reminders.add("appeler", due_at=4_000_000_000.0)

        registry = create_live_registry(
            memory_capability=memory,
            schedule_store=schedule,
            reminder_store=reminders,
        )
        tools = {t.info.name: t for t in registry.livekit_tools()}

        result = asyncio.run(tools["privacy_overview"]())

        self.assertTrue(result["ok"])
        self.assertEqual(result["memory_count"], 1)
        self.assertEqual(result["scheduled_count"], 1)
        self.assertEqual(result["reminder_count"], 1)
        # Journaling happens via the live tool wrapper, not direct capability calls.
        self.assertIsInstance(result["activity_count"], int)

    def test_empty_stores(self):
        tmp = Path(tempfile.mkdtemp())
        registry = create_live_registry(
            memory_capability=MemoryCapability(MemoryStore(tmp / "memory.db")),
            schedule_store=ScheduledMessageStore(path=tmp / "scheduled.db"),
            reminder_store=ReminderStore(path=tmp / "reminders.db"),
        )
        tools = {t.info.name: t for t in registry.livekit_tools()}

        result = asyncio.run(tools["privacy_overview"]())
        self.assertTrue(result["ok"])
        self.assertEqual(result["memory_count"], 0)
        self.assertEqual(result["scheduled_count"], 0)
        self.assertEqual(result["reminder_count"], 0)


if __name__ == "__main__":
    unittest.main()
