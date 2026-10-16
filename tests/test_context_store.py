import asyncio
import tempfile
import unittest
from pathlib import Path

from jarvis.context_store import ContextError, ContextStore
from jarvis.live.registry import create_live_registry


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        self.now += 1
        return self.now


def store():
    return ContextStore(path=Path(tempfile.mkdtemp()) / "context.db", clock=Clock())


class ContextStoreTests(unittest.TestCase):
    def test_add_and_recent_most_recent_first(self):
        s = store()
        s.add("on prepare la demo")
        s.add("on corrige le bug login")
        recent = s.recent()
        self.assertEqual(recent[0]["text"], "on corrige le bug login")
        self.assertEqual(len(recent), 2)

    def test_rolling_trim(self):
        s = store()
        for i in range(60):
            s.add(f"etape {i}")
        self.assertLessEqual(len(s.recent(limit=50)), 50)

    def test_invalid(self):
        with self.assertRaises(ContextError):
            store().add("   ")


class FakeMemory:
    def log_action(self, *a, **k):
        return None


class ContextToolsTests(unittest.TestCase):
    def _tools(self):
        s = ContextStore(path=Path(tempfile.mkdtemp()) / "context.db")
        registry = create_live_registry(context_store=s, memory_capability=FakeMemory())
        return {t.info.name: t for t in registry.livekit_tools()}, s

    def test_remember_then_recall(self):
        tools, s = self._tools()
        asyncio.run(tools["remember_context"]("on bosse sur le planner"))
        result = asyncio.run(tools["recall_context"]())
        self.assertTrue(result["ok"])
        self.assertIn("on bosse sur le planner", result["context"])

    def test_recall_empty(self):
        tools, s = self._tools()
        result = asyncio.run(tools["recall_context"]())
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 0)


if __name__ == "__main__":
    unittest.main()
