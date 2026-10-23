"""Local reminders: a note to self that fires a macOS notification at its time.

Simpler than a scheduled message (no recipient, no GUI send, so no confirmation
needed): it is the user's own note. Stored in a private (0600) SQLite DB and
delivered by the same launchd pass as scheduled messages, as a notification.
"""

from __future__ import annotations

import os
import math
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable


MAX_TEXT_LENGTH = 500
DEFAULT_LIST_LIMIT = 50

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    due_at REAL NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    done_at REAL,
    recurrence TEXT NOT NULL DEFAULT 'none'
);

CREATE INDEX IF NOT EXISTS reminders_due ON reminders(status, due_at);
"""

# Recurrence period in seconds (shared shape with scheduled messages).
RECURRENCES = {"daily": 86400.0, "weekly": 7 * 86400.0}


class ReminderError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


def default_reminders_path() -> Path:
    override = os.environ.get("JARVIS_REMINDERS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Jarvis" / "reminders.db"


class ReminderStore:
    def __init__(self, path: str | Path | None = None, clock: Callable[[], float] | None = None):
        self._path = Path(path).expanduser() if path is not None else None
        self._clock = clock if clock is not None else time.time
        self._initialized_path: Path | None = None

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else default_reminders_path()

    def add(self, text: str, due_at: float, recurrence: str = "none") -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ReminderError("Le texte du rappel est obligatoire.", "invalid_text")
        text = text.strip()
        if len(text) > MAX_TEXT_LENGTH:
            raise ReminderError("Le texte du rappel est trop long.", "invalid_text")
        try:
            if isinstance(due_at, bool):
                raise ValueError
            due = float(due_at)
            if not math.isfinite(due):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise ReminderError("La date du rappel est invalide.", "invalid_due_at")
        if recurrence is not None and not isinstance(recurrence, str):
            raise ReminderError("Recurrence inconnue.", "invalid_recurrence")
        recurrence = (recurrence or "none").strip().lower()
        if recurrence != "none" and recurrence not in RECURRENCES:
            raise ReminderError("Recurrence inconnue.", "invalid_recurrence")

        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO reminders (text, due_at, status, created_at, recurrence) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (text, due, self._clock(), recurrence),
            )
            row_id = cursor.lastrowid
        return self.get(row_id)

    def due(self, now: float | None = None) -> list[dict[str, Any]]:
        moment = self._clock() if now is None else float(now)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE status = 'pending' AND due_at <= ? "
                "ORDER BY due_at ASC",
                (moment,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list(self, status: str | None = "pending", limit: int = DEFAULT_LIST_LIMIT) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with closing(self._connect()) as conn:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM reminders ORDER BY due_at ASC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM reminders WHERE status = ? ORDER BY due_at ASC LIMIT ?",
                    (status, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def get(self, row_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (int(row_id),)
            ).fetchone()
        return dict(row) if row is not None else None

    def cancel(self, row_id: int) -> bool:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE reminders SET status = 'cancelled' "
                "WHERE id = ? AND status = 'pending'",
                (int(row_id),),
            )
            return cursor.rowcount > 0

    def mark_done(self, row_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE reminders SET status = 'done', done_at = ? WHERE id = ?",
                (self._clock(), int(row_id)),
            )

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
            try:
                conn.execute(
                    "ALTER TABLE reminders ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'none'"
                )
            except sqlite3.OperationalError:
                pass  # column already exists
            self._initialized_path = path
        return conn


def deliver_reminders(
    store: ReminderStore,
    *,
    now: float | None = None,
    notifier: Callable[[str], bool | None] | None = None,
) -> list[int]:
    """Deliver with serialized settlement and retry on notification failure.

    SQLite cannot transact with macOS notifications: a process crash after
    notification acceptance but before commit can still cause a retry. This is
    at-least-once recovery, not a guarantee of exactly-once presentation.
    """
    if notifier is None:
        return []
    moment = store._clock() if now is None else float(now)
    fired: list[int] = []
    for candidate in store.due(moment):
        with closing(store._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM reminders WHERE id=? AND status='pending' AND due_at<=?",
                (candidate['id'], moment),
            ).fetchone()
            if row is None:
                continue
            # Stage all database writes before the external effect. A failure
            # to create the next occurrence must not consume this reminder.
            conn.execute("UPDATE reminders SET status='done', done_at=? WHERE id=?",
                         (moment, row['id']))
            period = RECURRENCES.get(row['recurrence'])
            if period:
                nxt = row['due_at'] + (math.floor((moment-row['due_at']) / period) + 1) * period
                conn.execute(
                    "INSERT INTO reminders(text,due_at,status,created_at,recurrence) VALUES (?,?,'pending',?,?)",
                    (row['text'], nxt, store._clock(), row['recurrence']),
                )
            try:
                accepted = notifier(f"Rappel : {row['text']}")
            except Exception:
                conn.rollback()
                continue
            if accepted is False:
                conn.rollback()
                continue
        fired.append(row['id'])
    return fired
