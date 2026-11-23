"""Timers survive closing Jarvis as short reminders (idea 30)."""
import asyncio

from jarvis.capabilities.timers import TimerService
from jarvis.live.registry import create_live_registry
from jarvis.schedule.reminders import ReminderStore


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


async def never(_seconds):
    await asyncio.Event().wait()


def test_running_timers_are_handed_over_with_their_wall_clock_deadline():
    async def scenario():
        clock = Clock()
        service = TimerService(clock=clock, sleep=never, wall_clock=lambda: 50_000.0)
        long = service.start(600, "Pates").data
        short = service.start(3, "Oeuf").data
        cancelled = service.start(900, "Annule").data
        service.cancel(cancelled["id"])
        clock.now += 60
        handed = []
        await service.aclose(handoff=lambda label, due: handed.append((label, due)))
        return service, handed, long, short
    service, handed, long, short = asyncio.run(scenario())
    assert handed == [("Pates", 50_000.0 + 540)]  # 3 s left is too late to hand over
    assert service.timers[long["id"]]["state"] == "handed_off"
    assert service.timers[short["id"]]["state"] == "completed" or service.timers[short["id"]]["state"] == "cancelled"


def test_handoff_failure_is_recorded_without_raising():
    async def scenario():
        service = TimerService(clock=Clock(), sleep=never)
        timer = service.start(120, "Thé").data
        def broken(label, due): raise OSError("disk")
        await service.aclose(handoff=broken)
        return service.timers[timer["id"]]
    timer = asyncio.run(scenario())
    assert timer["state"] == "cancelled" and timer["handoff_failed"]


class FakeMemory:
    def resolve_person(self, name, app_name=None): return None
    def log_action(self, *args, **kwargs): return None


def test_registry_close_turns_a_running_timer_into_a_reminder(tmp_path):
    store = ReminderStore(path=tmp_path / "reminders.db")
    registry = create_live_registry(reminder_store=store, memory_capability=FakeMemory())
    tools = {tool.info.name: tool for tool in registry.livekit_tools()}

    async def scenario():
        started = await tools["start_timer"](900, "Four")
        await registry.aclose()
        return started
    started = asyncio.run(scenario())
    assert "rappel" in started["message"]
    rows = store.list("pending")
    assert [row["text"] for row in rows] == ["Minuteur « Four » termine"]
