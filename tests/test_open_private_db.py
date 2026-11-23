"""One helper opens every private SQLite database (idea 15)."""
import importlib
import inspect
import stat

import pytest

from jarvis.storage_privacy import open_private_db

STORES = ["jarvis.activity", "jarvis.macros", "jarvis.metrics.store", "jarvis.usage.store",
          "jarvis.schedule.store", "jarvis.schedule.reminders", "jarvis.context_store",
          "jarvis.memory.store", "jarvis.capabilities.checklists", "jarvis.desktop.result_history"]


def test_helper_creates_owner_only_files_with_secure_delete(tmp_path):
    path = tmp_path / "private" / "store.db"
    conn = open_private_db(path)
    try:
        assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
        conn.execute("CREATE TABLE t(x)")
        conn.execute("INSERT INTO t VALUES (1)")
        assert conn.execute("SELECT x FROM t").fetchone()["x"] == 1
    finally:
        conn.close()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_prepare_false_leaves_rights_alone(tmp_path):
    path = tmp_path / "store.db"
    path.touch(mode=0o644)
    path.chmod(0o644)
    open_private_db(path, prepare=False).close()
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


@pytest.mark.parametrize("module", STORES)
def test_stores_open_their_database_through_the_helper(module):
    source = inspect.getsource(importlib.import_module(module))
    assert "open_private_db(" in source
    assert "sqlite3.connect(" not in source
