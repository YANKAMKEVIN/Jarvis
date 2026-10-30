"""Local SQLite log of what Jarvis itself did, for the dashboard's Jarvis tab.

Three kinds of event, each a name and a time, never any content:
- "tool": a voice or mission tool was called (its name only, not the arguments);
- "wake": the wake word opened the microphone;
- "alert": an insight was raised (its title, message and severity).

Kept 30 days, file 0600, like the other private stores. Logging is
best-effort: `log_event` never raises, so a full disk or a locked file can
never break a tool call.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

ACTIVITY_RETENTION_SECONDS = 30 * 24 * 3600
ACTIVITY_KINDS = ("tool", "wake", "alert")
_MAX_NAME = 80
_MAX_DETAIL = 200

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_kind_ts ON events(kind, ts);
"""


def default_activity_db_path() -> Path:
    override = os.environ.get("JARVIS_ACTIVITY_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Jarvis" / "activity.db"


def _clean(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


class ActivityStore:
    def __init__(self, db_path: str | Path | None = None, clock: Callable[[], float] | None = None):
        self._db_path = Path(db_path).expanduser() if db_path is not None else None
        self._clock = clock if clock is not None else time.time
        self._initialized_path: Path | None = None

    @property
    def path(self) -> Path:
        return self._db_path if self._db_path is not None else default_activity_db_path()

    def record(self, kind: str, name: str, detail: str = "", level: str = "") -> None:
        if kind not in ACTIVITY_KINDS:
            raise ValueError(f"type d'événement inconnu: {kind}")
        name = _clean(name, _MAX_NAME)
        if not name:
            return
        conn = self._connect()
        try:
            conn.execute("INSERT INTO events (ts, kind, name, detail, level) VALUES (?, ?, ?, ?, ?)",
                         (self._clock(), kind, name, _clean(detail, _MAX_DETAIL), _clean(level, 16)))
            conn.commit()
        finally:
            conn.close()

    def count(self, kind: str, since: float | None = None) -> int:
        conn = self._connect()
        try:
            return int(conn.execute(
                "SELECT COUNT(*) n FROM events WHERE kind = ? AND ts >= ?",
                (kind, since if since is not None else 0.0),
            ).fetchone()["n"])
        finally:
            conn.close()

    def top(self, kind: str, since: float | None = None, limit: int = 8) -> list[dict[str, Any]]:
        """Most frequent names of one kind, most used first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT name, COUNT(*) n, MAX(ts) last_ts FROM events "
                "WHERE kind = ? AND ts >= ? GROUP BY name ORDER BY n DESC, last_ts DESC LIMIT ?",
                (kind, since if since is not None else 0.0, max(1, int(limit))),
            ).fetchall()
            return [{"name": r["name"], "count": int(r["n"]), "last_ts": r["last_ts"]} for r in rows]
        finally:
            conn.close()

    def recent(self, kind: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT ts, name, detail, level FROM events WHERE kind = ? "
                "ORDER BY ts DESC, id DESC LIMIT ?",
                (kind, max(1, min(int(limit), 200))),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def clear(self) -> int:
        conn = self._connect()
        try:
            removed = conn.execute("DELETE FROM events").rowcount
            conn.commit()
            return int(removed or 0)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        path = self.path
        initialized = self._initialized_path == path and path.exists()
        if not initialized:
            path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(path.parent, 0o700)
            if not path.exists():
                path.touch(mode=0o600)
            os.chmod(path, 0o600)
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        if not initialized:
            conn.executescript(_SCHEMA)
            self._initialized_path = path
        conn.execute("DELETE FROM events WHERE ts <= ?",
                     (self._clock() - ACTIVITY_RETENTION_SECONDS,))
        return conn


_default: ActivityStore | None = None


def default_store() -> ActivityStore:
    global _default
    if _default is None:
        _default = ActivityStore()
    return _default


def log_event(kind: str, name: str, detail: str = "", level: str = "",
              store: ActivityStore | None = None) -> None:
    """Record one event; never raises."""
    if os.environ.get("JARVIS_ACTIVITY_DISABLED"):
        return
    try:
        (store or default_store()).record(kind, name, detail, level)
    except Exception:
        pass
