"""Named goal macros: a reusable multi-step workflow defined by the user.

A macro maps a short name to a natural-language goal; running it launches a
planner task with that goal. Distinct from learned procedures (which capture a
tool skeleton after a task succeeds): a macro is authored up front. Stored in a
private (0600) SQLite DB outside the repo.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable


MAX_NAME_LENGTH = 80
MAX_GOAL_LENGTH = 500
DEFAULT_LIST_LIMIT = 50

_SCHEMA = """
CREATE TABLE IF NOT EXISTS macros (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    goal TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


class MacroError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


def default_macros_path() -> Path:
    override = os.environ.get("JARVIS_MACROS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Jarvis" / "macros.db"


def _key(name: str) -> str:
    return " ".join(name.strip().lower().split())


class MacroStore:
    def __init__(self, path: str | Path | None = None, clock: Callable[[], float] | None = None):
        self._path = Path(path).expanduser() if path is not None else None
        self._clock = clock if clock is not None else time.time

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else default_macros_path()

    def save(self, name: str, goal: str) -> dict[str, Any]:
        name = self._require(name, "name", MAX_NAME_LENGTH)
        goal = self._require(goal, "goal", MAX_GOAL_LENGTH)
        now = self._clock()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO macros (name, name_key, goal, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(name_key) DO UPDATE SET name=excluded.name, "
                "goal=excluded.goal, updated_at=excluded.updated_at",
                (name, _key(name), goal, now, now),
            )
        return self.get(name)

    def get(self, name: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM macros WHERE name_key = ?", (_key(name),)
            ).fetchone()
        return dict(row) if row is not None else None

    def list(self, limit: int = DEFAULT_LIST_LIMIT) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM macros ORDER BY name ASC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, name: str) -> bool:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute("DELETE FROM macros WHERE name_key = ?", (_key(name),))
            return cursor.rowcount > 0

    @staticmethod
    def _require(value: Any, field: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise MacroError(f"Le champ {field} est obligatoire.", f"invalid_{field}")
        trimmed = value.strip()
        if len(trimmed) > max_length:
            raise MacroError(f"Le champ {field} est trop long.", f"invalid_{field}")
        return trimmed

    def _connect(self) -> sqlite3.Connection:
        path = self.path
        if not (path.exists()):
            path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(path.parent, 0o700)
            path.touch(mode=0o600)
            os.chmod(path, 0o600)
            conn = sqlite3.connect(path, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.executescript(_SCHEMA)
            return conn
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn
