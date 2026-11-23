"""Every local SQLite store erases deleted bytes (idea 14)."""
from contextlib import closing

import pytest

from jarvis.activity import ActivityStore
from jarvis.macros import MacroStore
from jarvis.metrics.store import MetricsStore
from jarvis.usage.store import UsageStore

SENTINEL = "qaSecureDeleteSentinelFictionOnly4417"


def stores(tmp_path):
    return {
        "activity": ActivityStore(tmp_path / "activity.db"),
        "macros": MacroStore(tmp_path / "macros.db"),
        "metrics": MetricsStore(tmp_path / "metrics.db"),
        "usage": UsageStore(db_path=tmp_path / "usage.db", projects_dir=tmp_path / "projects"),
    }


@pytest.mark.parametrize("name", ["activity", "macros", "metrics", "usage"])
def test_connections_enable_secure_delete(tmp_path, name):
    store = stores(tmp_path)[name]
    with closing(store._connect()) as conn:
        assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1


def test_activity_clear_removes_bytes_from_the_file(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    store.record("tool", "open_app", SENTINEL)
    assert store.clear() == 1
    assert SENTINEL.encode() not in store.path.read_bytes()


def test_deleted_macro_leaves_no_bytes_in_the_file(tmp_path):
    store = MacroStore(tmp_path / "macros.db")
    store.save("reunion", SENTINEL)
    assert store.delete("reunion")
    assert SENTINEL.encode() not in store.path.read_bytes()
