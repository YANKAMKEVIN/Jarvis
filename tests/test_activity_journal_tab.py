"""Journal tab: read and erase the activity journal by period (idea 43)."""
import asyncio
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from jarvis.activity import ActivityStore
from jarvis.desktop.journal_page import JournalPage

NOW = 1_800_000_000.0
DAY = 86400


def store(tmp_path):
    clock = [NOW - 20 * DAY]
    s = ActivityStore(tmp_path / "activity.db", clock=lambda: clock[0])
    for offset, kind, name, level in ((20, "tool", "open_app", "ok"), (3, "tool", "send_message", "error"),
                                      (3, "wake", "hey_jarvis", ""), (0.01, "tool", "get_volume", "ok")):
        clock[0] = NOW - offset * DAY
        s.record(kind, name, level=level)
    clock[0] = NOW
    return s


def test_query_and_delete_range(tmp_path):
    s = store(tmp_path)
    assert [r["name"] for r in s.query(since=NOW - 7 * DAY)] == ["get_volume", "hey_jarvis", "send_message"]
    assert [r["name"] for r in s.query(kind="tool", level="error", since=0)] == ["send_message"]
    assert s.delete_range(NOW - 7 * DAY, kind="tool") == 2
    assert [r["name"] for r in s.query(since=0)] == ["hey_jarvis", "open_app"]


def test_tab_filters_and_erases_after_confirmation(tmp_path):
    QApplication.instance() or QApplication([])
    s = store(tmp_path)
    answers = []
    page = JournalPage(store=s, clock=lambda: NOW, confirm=lambda text: answers.append(text) or len(answers) > 1)
    page.period.setCurrentIndex(page.period.findData("30d"))
    assert page.table.rowCount() == 4
    page.level.setCurrentIndex(page.level.findData("error"))
    assert page.table.rowCount() == 1 and page.table.item(0, 2).text() == "send_message"
    page.level.setCurrentIndex(0)
    page.period.setCurrentIndex(page.period.findData("7d"))
    assert page.erase_period() == 0 and page.table.rowCount() == 3  # refused confirmation
    assert page.erase_period() == 3 and page.table.rowCount() == 0
    assert [r["name"] for r in s.query(since=0)] == ["open_app"]


class FakeMemory:
    def resolve_person(self, *a, **k): return None
    def log_action(self, *a, **k): return None


def test_tool_calls_are_logged_with_their_outcome(tmp_path, monkeypatch):
    from jarvis.live.registry import create_live_registry
    monkeypatch.delenv("JARVIS_ACTIVITY_DISABLED", raising=False)
    journal = ActivityStore(tmp_path / "a.db")
    monkeypatch.setattr("jarvis.activity._default", journal)
    registry = create_live_registry(memory_capability=FakeMemory())
    tools = {t.info.name: t for t in registry.livekit_tools()}
    asyncio.run(tools["calculate"]("2+2"))
    asyncio.run(tools["calculate"]("import os"))
    registry.read_only_mode = True
    asyncio.run(tools["open_app"]("Notes"))
    levels = [(r["name"], r["level"]) for r in journal.query(kind="tool", since=0)]
    assert levels == [("open_app", "refused"), ("calculate", "error"), ("calculate", "ok")]
