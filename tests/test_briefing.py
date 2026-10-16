import asyncio
import unittest

from jarvis.capabilities.results import ToolResult
from jarvis.live.registry import create_live_registry


class FakeKnowledge:
    def __init__(self, message="Trois grands titres ce matin."):
        self.message = message
        self.calls = []

    def answer(self, question):
        self.calls.append(question)
        return ToolResult.success(
            action="web_answer", message=self.message,
            external_knowledge_retrieved=True, state_confirmed=True, sources=[],
            source_count=0,
        )


class FakeCalendar:
    def __init__(self, ok=True, count=2):
        self._ok = ok
        self._count = count

    def list_today(self, day_offset=0):
        if not self._ok:
            return ToolResult.failure(
                action="list_calendar_events", message="ko", error_code="calendar_timeout",
            )
        return ToolResult.success(
            action="list_calendar_events", message="ok",
            events=[], event_count=self._count,
        )


class FakeMemory:
    def log_action(self, *a, **k):
        return None


class BriefingTest(unittest.TestCase):
    def _run(self, calendar, knowledge):
        async def scenario():
            registry = create_live_registry(
                knowledge_capability=knowledge,
                calendar_capability=calendar,
                memory_capability=FakeMemory(),
            )
            spoken = []

            async def notifier(text):
                spoken.append(text)

            registry.set_task_notifier(notifier)
            tools = {t.info.name: t for t in registry.livekit_tools()}
            ack = await tools["morning_briefing"]()
            await registry._briefing_task
            return ack, spoken

        return asyncio.run(scenario())

    def test_briefing_assembles_date_agenda_news(self):
        ack, spoken = self._run(FakeCalendar(ok=True, count=2), FakeKnowledge())
        self.assertTrue(ack["ok"])
        self.assertTrue(ack["briefing_started"])
        self.assertEqual(len(spoken), 1)
        self.assertIn("evenement", spoken[0])
        self.assertIn("Trois grands titres", spoken[0])

    def test_briefing_tolerates_unavailable_calendar(self):
        ack, spoken = self._run(FakeCalendar(ok=False), FakeKnowledge())
        self.assertTrue(ack["ok"])
        self.assertIn("agenda non disponible", spoken[0])
        self.assertIn("Trois grands titres", spoken[0])


if __name__ == "__main__":
    unittest.main()
