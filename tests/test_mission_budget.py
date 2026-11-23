"""Mission timeline shows the planner budget: « Étape 4/25 · 40 s sur 180 » (idea 38)."""
import asyncio

from jarvis.desktop.presentation import mission_progress, project_task
from jarvis.planner import ModelTurn, PlannerEngine, ScriptedModel
from jarvis.planner.tasks import TaskManager


def test_projection_keeps_only_a_valid_budget():
    running = project_task({"id": "m", "status": "running", "current_tool": "web_answer", "steps": [{"tool": "open_app", "ok": True}] * 3,
                            "elapsed_seconds": 40, "max_steps": 25, "max_seconds": 180})
    assert mission_progress(running) == "Étape 4/25 · 40 s sur 180"
    idle = {**running, "current": ""}
    assert mission_progress(idle) == "Étape 3/25 · 40 s sur 180"
    finished = {**running, "status": "completed"}
    assert mission_progress(finished) == "3 étapes traitées"
    broken = project_task({"id": "m", "status": "running", "steps": [], "elapsed_seconds": "40", "max_steps": 25, "max_seconds": 180})
    assert "max_steps" not in broken


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


def test_task_manager_snapshot_carries_elapsed_time_and_engine_budget():
    clock = Clock()
    seen = {}

    async def scenario():
        gate = asyncio.Event()

        class SlowModel(ScriptedModel):
            def complete(self, messages, tools):
                clock.now = 42.0
                seen["running"] = manager.progress()
                return ModelTurn(text="fini")

        manager = TaskManager(lambda: PlannerEngine(SlowModel([]), [], max_steps=25, max_seconds=180), clock=clock)
        manager.start("Range le bureau")
        await manager.wait()
        seen["done"] = manager.progress()
        gate.set()

    asyncio.run(scenario())
    running = seen["running"]
    assert running["max_steps"] == 25 and running["max_seconds"] == 180
    assert running["elapsed_seconds"] in (0, 42)
    assert "elapsed_seconds" not in seen["done"]
