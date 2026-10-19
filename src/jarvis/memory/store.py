"""Local, private long-term memory for Jarvis (SQLite + FTS5).

The database lives outside the repository, readable by the user only. It is
opened lazily (constructing a store touches nothing on disk) and one short
connection is used per operation, so the store is safe to call from the worker
threads LiveKit tools run in.

Memory is never pushed into the model's prompt: tools read it locally and
apply it (e.g. alias -> contact name), and only explicit recall results are
returned to the model.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jarvis.tools.accessibility import normalize_text


MEMORY_KINDS = ("profile", "person", "preference", "fact", "procedure")
MEMORY_SOURCES = ("user", "inferred")

EPISODE_RETENTION_SECONDS = 30 * 24 * 3600
MAX_EPISODE_FIELD_LENGTH = 80

# Mission history survives restarts (the running coroutine does not): only the
# objective, final status and step count are kept, with the same 30-day
# retention as the activity journal.
MISSION_RETENTION_SECONDS = EPISODE_RETENTION_SECONDS
MAX_MISSION_GOAL_LENGTH = 200
MAX_MISSION_STATUS_LENGTH = 40

MAX_SUBJECT_LENGTH = 120
MAX_CONTENT_LENGTH = 500
# A learned procedure stores a small JSON plan (tool + target per step), which
# needs more room than a one-line fact.
MAX_PROCEDURE_CONTENT_LENGTH = 2000
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_LIST_LIMIT = 50

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_used_at REAL,
    expires_at REAL,
    UNIQUE (kind, subject_key)
);

-- Activity journal: what Jarvis did, never the content it handled (no
-- message text, clipboard, typed text or file paths). Kept 30 days.
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    at REAL NOT NULL,
    tool TEXT NOT NULL,
    target TEXT,
    ok INTEGER NOT NULL,
    error_code TEXT
);

CREATE INDEX IF NOT EXISTS episodes_at ON episodes(at);

-- Mission history: the objective, final status and step count of finished
-- background missions. It survives a restart (the live task does not). Kept
-- 30 days. No step arguments, tool results or message content.
CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY,
    at REAL NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    step_count INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS missions_at ON missions(at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    subject,
    content,
    content='memories',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, subject, content)
    VALUES (new.id, new.subject, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, subject, content)
    VALUES ('delete', old.id, old.subject, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, subject, content)
    VALUES ('delete', old.id, old.subject, old.content);
    INSERT INTO memories_fts(rowid, subject, content)
    VALUES (new.id, new.subject, new.content);
END;
"""

_TOKEN_PATTERN = re.compile(r"[\w']+", re.UNICODE)


class MemoryError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class Memory:
    id: int
    kind: str
    subject: str
    content: str
    source: str
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "subject": self.subject,
            "content": self.content,
            "source": self.source,
        }


@dataclass(frozen=True)
class Episode:
    id: int
    at: float
    tool: str
    target: str | None
    ok: bool
    error_code: str | None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "at": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.at)),
            "tool": self.tool,
            "ok": self.ok,
        }
        if self.target:
            payload["target"] = self.target
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload


@dataclass(frozen=True)
class Mission:
    id: int
    at: float
    goal: str
    status: str
    step_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.at)),
            "goal": self.goal,
            "status": self.status,
            "step_count": self.step_count,
        }


def default_memory_path() -> Path:
    override = os.environ.get("JARVIS_MEMORY_PATH")
    if override:
        return Path(override).expanduser()

    return Path.home() / "Library" / "Application Support" / "Jarvis" / "memory.db"


def subject_key(subject: str) -> str:
    return normalize_text(subject)


class MemoryStore:
    def __init__(
        self,
        path: str | Path | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._path = Path(path).expanduser() if path is not None else None
        self._clock = clock if clock is not None else time.time
        self._initialized_path: Path | None = None

    @property
    def path(self) -> Path:
        # Resolved lazily so JARVIS_MEMORY_PATH set after construction applies.
        return self._path if self._path is not None else default_memory_path()

    # --- public API -----------------------------------------------------------

    def remember(
        self,
        kind: str,
        subject: str,
        content: str,
        source: str = "user",
    ) -> tuple[Memory, bool]:
        """Insert or update (same kind + subject). Returns (memory, created)."""
        kind, subject, content, source = self.validate(kind, subject, content, source)
        key = subject_key(subject)
        now = self._clock()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM memories WHERE kind = ? AND subject_key = ?",
                (kind, key),
            ).fetchone()

            if row is None:
                cursor = conn.execute(
                    "INSERT INTO memories (kind, subject, subject_key, content, source,"
                    " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (kind, subject, key, content, source, now, now),
                )
                memory_id, created = cursor.lastrowid, True
            else:
                memory_id, created = row["id"], False
                conn.execute(
                    "UPDATE memories SET subject = ?, content = ?, source = ?,"
                    " updated_at = ? WHERE id = ?",
                    (subject, content, source, now, memory_id),
                )

            return self._get(conn, memory_id), created

    @classmethod
    def validate(
        cls,
        kind: str,
        subject: str,
        content: str,
        source: str = "user",
    ) -> tuple[str, str, str, str]:
        """Normalized (kind, subject, content, source); raises MemoryError."""
        kind = cls._validate_kind(kind)
        subject = cls._validate_text(subject, "subject", MAX_SUBJECT_LENGTH)
        content_max = (
            MAX_PROCEDURE_CONTENT_LENGTH if kind == "procedure" else MAX_CONTENT_LENGTH
        )
        content = cls._validate_text(content, "content", content_max)
        if source not in MEMORY_SOURCES:
            raise MemoryError("Source de souvenir invalide.", "invalid_source")
        return kind, subject, content, source

    def get(self, memory_id: int) -> Memory | None:
        with self._connect() as conn:
            return self._get(conn, memory_id)

    def find_by_subject(self, kind: str, subject: str) -> Memory | None:
        """Exact (normalized) subject lookup, used by tools applying memory."""
        if kind not in MEMORY_KINDS or not isinstance(subject, str) or not subject.strip():
            return None

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE kind = ? AND subject_key = ?",
                (kind, subject_key(subject)),
            ).fetchone()
            if row is None:
                return None
            self._touch(conn, [row["id"]])
            return self._from_row(row)

    def search(
        self,
        query: str,
        kind: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[Memory]:
        if kind is not None:
            kind = self._validate_kind(kind)
        tokens = [t for t in _TOKEN_PATTERN.findall(normalize_text(query or "")) if len(t) > 1]
        if not tokens:
            raise MemoryError("La recherche ne peut pas etre vide.", "invalid_query")

        limit = max(1, min(int(limit), DEFAULT_LIST_LIMIT))
        quoted = ['"' + t.replace('"', "") + '"*' for t in tokens]

        with self._connect() as conn:
            # All words first; fall back to any word so a partial phrasing
            # ("dentiste" for "mon dentiste est le Dr Martin") still matches.
            for operator in (" AND ", " OR "):
                rows = self._fts(conn, operator.join(quoted), kind, limit)
                if rows:
                    break
            self._touch(conn, [row["id"] for row in rows])
            return [self._from_row(row) for row in rows]

    def list(self, kind: str | None = None, limit: int = DEFAULT_LIST_LIMIT) -> list[Memory]:
        if kind is not None:
            kind = self._validate_kind(kind)
        limit = max(1, min(int(limit), 200))

        with self._connect() as conn:
            if kind is None:
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY kind, subject_key LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE kind = ? ORDER BY subject_key LIMIT ?",
                    (kind, limit),
                ).fetchall()
            return [self._from_row(row) for row in rows]

    def delete(self, memory_id: int) -> Memory | None:
        with self._connect() as conn:
            memory = self._get(conn, memory_id)
            if memory is not None:
                conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return memory

    def log_episode(
        self,
        tool: str,
        target: str | None = None,
        ok: bool = True,
        error_code: str | None = None,
    ) -> None:
        def clip(value):
            if not isinstance(value, str) or not value.strip():
                return None
            return " ".join(value.split())[:MAX_EPISODE_FIELD_LENGTH]

        tool = clip(tool)
        if tool is None:
            raise MemoryError("Nom d'action invalide.", "invalid_tool")

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO episodes (at, tool, target, ok, error_code) VALUES (?, ?, ?, ?, ?)",
                (self._clock(), tool, clip(target), 1 if ok else 0, clip(error_code)),
            )

    def recent_episodes(self, limit: int = 20) -> list[Episode]:
        limit = max(1, min(int(limit), 100))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM episodes ORDER BY at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            Episode(
                id=row["id"],
                at=row["at"],
                tool=row["tool"],
                target=row["target"],
                ok=bool(row["ok"]),
                error_code=row["error_code"],
            )
            for row in rows
        ]

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def log_mission(self, goal: str, status: str, step_count: int = 0) -> None:
        """Record a finished mission (objective + final status), never content."""
        goal = " ".join(goal.split())[:MAX_MISSION_GOAL_LENGTH] if isinstance(goal, str) else ""
        if not goal:
            goal = "(objectif indisponible)"
        status = (" ".join(status.split())[:MAX_MISSION_STATUS_LENGTH]
                  if isinstance(status, str) and status.strip() else "unknown")
        try:
            step_count = max(0, int(step_count))
        except (TypeError, ValueError):
            step_count = 0

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO missions (at, goal, status, step_count) VALUES (?, ?, ?, ?)",
                (self._clock(), goal, status, step_count),
            )

    def recent_missions(self, limit: int = 20) -> list[Mission]:
        limit = max(1, min(int(limit), 100))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM missions ORDER BY at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            Mission(
                id=row["id"],
                at=row["at"],
                goal=row["goal"],
                status=row["status"],
                step_count=row["step_count"],
            )
            for row in rows
        ]

    def clear_missions(self) -> int:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0]
            conn.execute("DELETE FROM missions")
            return count

    # --- internals ------------------------------------------------------------

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

        now = self._clock()
        conn.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )
        conn.execute(
            "DELETE FROM episodes WHERE at <= ?",
            (now - EPISODE_RETENTION_SECONDS,),
        )
        conn.execute(
            "DELETE FROM missions WHERE at <= ?",
            (now - MISSION_RETENTION_SECONDS,),
        )
        return _ClosingConnection(conn)

    @staticmethod
    def _fts(conn, match: str, kind: str | None, limit: int):
        sql = (
            "SELECT m.* FROM memories_fts f JOIN memories m ON m.id = f.rowid"
            " WHERE memories_fts MATCH ?"
        )
        params: list[Any] = [match]
        if kind is not None:
            sql += " AND m.kind = ?"
            params.append(kind)
        sql += " ORDER BY bm25(memories_fts) LIMIT ?"
        params.append(limit)
        return conn.execute(sql, params).fetchall()

    def _touch(self, conn, ids: list[int]) -> None:
        if ids:
            conn.executemany(
                "UPDATE memories SET last_used_at = ? WHERE id = ?",
                [(self._clock(), memory_id) for memory_id in ids],
            )

    def _get(self, conn, memory_id: int) -> Memory | None:
        if not isinstance(memory_id, int) or isinstance(memory_id, bool):
            raise MemoryError("Identifiant de souvenir invalide.", "invalid_memory_id")
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._from_row(row) if row is not None else None

    @staticmethod
    def _from_row(row) -> Memory:
        return Memory(
            id=row["id"],
            kind=row["kind"],
            subject=row["subject"],
            content=row["content"],
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _validate_kind(kind: str) -> str:
        if not isinstance(kind, str) or kind.strip().casefold() not in MEMORY_KINDS:
            raise MemoryError(
                f"Type de souvenir invalide (attendu : {', '.join(MEMORY_KINDS)}).",
                "invalid_kind",
            )
        return kind.strip().casefold()

    @staticmethod
    def _validate_text(value: str, field: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise MemoryError(f"Le champ {field} est obligatoire.", f"invalid_{field}")
        value = " ".join(value.split())
        if len(value) > max_length:
            raise MemoryError(
                f"Le champ {field} est trop long ({max_length} caracteres max).",
                f"{field}_too_long",
            )
        return value


class _ClosingConnection:
    """Context manager: commit on success, roll back on error, always close."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
