"""Rolling conversation context across sessions.

Short notes the assistant records about what is going on ("on prepare la demo
de vendredi"), so a later session can pick up with "reprends ou on en etait".
Private (0600) SQLite DB outside the repo; distinct from long-term memory
(facts/preferences) and from dictated notes.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable


MAX_TEXT_LENGTH = 1000
DEFAULT_RECENT = 5
# Keep only the most recent entries to stay a rolling summary, not a log.
MAX_ENTRIES = 50

_SCHEMA = """
CREATE TABLE IF NOT EXISTS context (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS context_at ON context(at);
"""


class ContextError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


def default_context_path() -> Path:
    override = os.environ.get("JARVIS_CONTEXT_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Jarvis" / "context.db"


class ContextStore:
    def __init__(self, path: str | Path | None = None, clock: Callable[[], float] | None = None):
        self._path = Path(path).expanduser() if path is not None else None
        self._clock = clock if clock is not None else time.time

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else default_context_path()

    def add(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ContextError("Le contexte est vide.", "invalid_text")
        trimmed = text.strip()[:MAX_TEXT_LENGTH]
        now = self._clock()
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO context (text, at) VALUES (?, ?)", (trimmed, now)
            )
            # Trim to the most recent MAX_ENTRIES.
            conn.execute(
                "DELETE FROM context WHERE id NOT IN "
                "(SELECT id FROM context ORDER BY at DESC LIMIT ?)",
                (MAX_ENTRIES,),
            )
            row_id = cursor.lastrowid
        return {"id": row_id, "text": trimmed, "at": now}

    def update(self, entry_id: int, text: str) -> bool:
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > MAX_TEXT_LENGTH:
            raise ContextError("Texte vide ou trop long.", "invalid_text")
        with closing(self._connect()) as conn, conn:
            return bool(conn.execute("UPDATE context SET text = ? WHERE id = ?", (text.strip(), int(entry_id))).rowcount)

    def delete(self, entry_id: int) -> bool:
        with closing(self._connect()) as conn, conn:
            return bool(conn.execute("DELETE FROM context WHERE id = ?", (int(entry_id),)).rowcount)

    def clear(self) -> int:
        """Delete all context entries. Returns how many were removed."""
        with closing(self._connect()) as conn, conn:
            before = conn.execute("SELECT COUNT(*) FROM context").fetchone()[0]
            conn.execute("DELETE FROM context")
            return int(before)

    def recent(self, limit: int = DEFAULT_RECENT) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), MAX_ENTRIES))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM context ORDER BY at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        path = self.path
        existed = path.exists()
        if not existed:
            path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(path.parent, 0o700)
            path.touch(mode=0o600)
            os.chmod(path, 0o600)
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn
