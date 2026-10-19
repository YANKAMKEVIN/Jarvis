import asyncio
import tempfile
import unittest
from pathlib import Path

from jarvis.capabilities.memory import MemoryCapability
from jarvis.live.registry import create_live_registry
from jarvis.memory.store import MISSION_RETENTION_SECONDS, MemoryStore
from jarvis.planner.engine import TaskOutcome


class MissionStoreTests(unittest.TestCase):
    def _store(self, clock=None):
        tmp = Path(tempfile.mkdtemp())
        return MemoryStore(path=tmp / "memory.db", clock=clock)

    def test_log_and_read_back_most_recent_first(self):
        store = self._store()
        store.log_mission("ranger le bureau", "completed", 4)
        store.log_mission("comparer deux notes", "failed", 2)
        missions = store.recent_missions(10)
        self.assertEqual([m.goal for m in missions],
                         ["comparer deux notes", "ranger le bureau"])
        self.assertEqual(missions[0].status, "failed")
        self.assertEqual(missions[1].step_count, 4)

    def test_limit_is_respected(self):
        store = self._store()
        for i in range(5):
            store.log_mission(f"mission {i}", "completed", 1)
        self.assertEqual(len(store.recent_missions(3)), 3)

    def test_junk_goal_is_stored_safely(self):
        store = self._store()
        store.log_mission("   ", "", -3)
        mission = store.recent_missions(1)[0]
        self.assertEqual(mission.goal, "(objectif indisponible)")
        self.assertEqual(mission.status, "unknown")
        self.assertEqual(mission.step_count, 0)

    def test_retention_purges_old_missions(self):
        now = [1_000_000.0]
        store = self._store(clock=lambda: now[0])
        store.log_mission("vieille mission", "completed", 1)
        self.assertEqual(len(store.recent_missions(10)), 1)
        now[0] += MISSION_RETENTION_SECONDS + 1
        self.assertEqual(store.recent_missions(10), [])

    def test_clear_returns_count_and_empties(self):
        store = self._store()
        store.log_mission("a", "completed", 1)
        store.log_mission("b", "cancelled", 0)
        self.assertEqual(store.clear_missions(), 2)
        self.assertEqual(store.recent_missions(10), [])


class MissionHistoryIntegrationTests(unittest.TestCase):
    def _registry(self, memory_path):
        registry = create_live_registry(
            memory_capability=MemoryCapability(MemoryStore(path=memory_path)),
        )
        tools = {t.info.name: t for t in registry.livekit_tools()}
        return registry, tools

    def test_finished_mission_is_persisted_and_survives_restart(self):
        tmp = Path(tempfile.mkdtemp())
        memory_path = tmp / "memory.db"

        registry, tools = self._registry(memory_path)
        asyncio.run(registry._on_task_finished(
            "ranger le bureau", TaskOutcome("completed", "ok", [])))

        result = asyncio.run(tools["recent_missions"](10))
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["missions"][0]["goal"], "ranger le bureau")
        self.assertEqual(result["missions"][0]["status"], "completed")

        # Fresh registry on the same store = a restart: history is still there.
        _, tools_after_restart = self._registry(memory_path)
        after = asyncio.run(tools_after_restart["recent_missions"](10))
        self.assertEqual(after["count"], 1)
        self.assertEqual(after["missions"][0]["goal"], "ranger le bureau")

    def test_clear_personal_data_missions_scope(self):
        tmp = Path(tempfile.mkdtemp())
        registry, tools = self._registry(tmp / "memory.db")
        asyncio.run(registry._on_task_finished(
            "mission a oublier", TaskOutcome("failed", "ko", [])))

        prep = asyncio.run(tools["clear_personal_data"]("missions"))
        self.assertTrue(prep["requires_confirmation"])
        confirmed = asyncio.run(tools["confirm_action"](prep["token"]))
        self.assertTrue(confirmed["ok"])
        self.assertEqual(confirmed["cleared"].get("missions"), 1)

        after = asyncio.run(tools["recent_missions"](10))
        self.assertEqual(after["count"], 0)

    def test_privacy_overview_reports_missions(self):
        tmp = Path(tempfile.mkdtemp())
        registry, tools = self._registry(tmp / "memory.db")
        asyncio.run(registry._on_task_finished(
            "une mission", TaskOutcome("completed", "ok", [])))
        overview = asyncio.run(tools["privacy_overview"]())
        self.assertEqual(overview["mission_count"], 1)


if __name__ == "__main__":
    unittest.main()
