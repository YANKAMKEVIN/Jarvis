"""Local store of scheduled WhatsApp (and other messaging) sends.

A scheduled send is authorized once, when it is created (the user confirms the
app, recipient, text and time). The row holds that intent until a delivery pass
sends it. The database lives outside the repo, readable by the user only, and
holds message content (needed to send), so it is chmod 0600.

Delivery itself re-verifies the recipient at send time and fails safe; this
module only stores and transitions rows.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable


STATUSES = ("pending", "sent", "failed", "cancelled")

MAX_TEXT_LENGTH = 4000
MAX_RECIPIENT_LENGTH = 200
MAX_APP_LENGTH = 80
DEFAULT_LIST_LIMIT = 50

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled (
    id INTEGER PRIMARY KEY,
    app TEXT NOT NULL,
    recipient TEXT NOT NULL,
    text TEXT NOT NULL,
    due_at REAL NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at REAL NOT NULL,
    sent_at REAL
);

CREATE INDEX IF NOT EXISTS scheduled_due ON scheduled(status, due_at);
"""


class ScheduleError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


def default_schedule_path() -> Path:
    override = os.environ.get("JARVIS_SCHEDULE_PATH")
    if override:
        return Path(override).expanduser()

    return Path.home() / "Library" / "Application Support" / "Jarvis" / "scheduled.db"


class ScheduledMessageStore:
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
        return self._path if self._path is not None else default_schedule_path()

    # --- public API ----------------------------------------------------------

    def add(self, app: str, recipient: str, text: str, due_at: float) -> dict[str, Any]:
        app = self._require(app, "app", MAX_APP_LENGTH, "invalid_app")
        recipient = self._require(
            recipient, "recipient", MAX_RECIPIENT_LENGTH, "invalid_recipient"
        )
        text = self._require(text, "text", MAX_TEXT_LENGTH, "invalid_text")
        try:
            due = float(due_at)
        except (TypeError, ValueError):
            raise ScheduleError("La date d'envoi est invalide.", "invalid_due_at")

        now = self._clock()
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO scheduled (app, recipient, text, due_at, status, "
                "attempts, created_at) VALUES (?, ?, ?, ?, 'pending', 0, ?)",
                (app, recipient, text, due, now),
            )
            row_id = cursor.lastrowid
        return self.get(row_id)

    def due(self, now: float | None = None) -> list[dict[str, Any]]:
        moment = self._clock() if now is None else float(now)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled WHERE status = 'pending' AND due_at <= ? "
                "ORDER BY due_at ASC",
                (moment,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list(self, status: str | None = None, limit: int = DEFAULT_LIST_LIMIT) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with closing(self._connect()) as conn:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM scheduled ORDER BY due_at ASC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scheduled WHERE status = ? ORDER BY due_at ASC LIMIT ?",
                    (status, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def get(self, row_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM scheduled WHERE id = ?", (int(row_id),)
            ).fetchone()
        return dict(row) if row is not None else None

    def cancel(self, row_id: int) -> bool:
        """Cancel a still-pending message. Returns whether a row changed."""
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE scheduled SET status = 'cancelled' "
                "WHERE id = ? AND status = 'pending'",
                (int(row_id),),
            )
            return cursor.rowcount > 0

    def mark_sent(self, row_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE scheduled SET status = 'sent', sent_at = ?, last_error = NULL "
                "WHERE id = ?",
                (self._clock(), int(row_id)),
            )

    def mark_failed(self, row_id: int, error: str | None = None) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE scheduled SET status = 'failed', last_error = ?, "
                "attempts = attempts + 1 WHERE id = ?",
                (self._trim(error), int(row_id)),
            )

    def record_attempt(self, row_id: int, error: str | None = None) -> None:
        """A delivery pass tried but deferred (e.g. screen locked): keep it
        pending, bump the attempt count and note why."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE scheduled SET attempts = attempts + 1, last_error = ? "
                "WHERE id = ? AND status = 'pending'",
                (self._trim(error), int(row_id)),
            )

    # --- internals -----------------------------------------------------------

    @staticmethod
    def _require(value: Any, field: str, max_length: int, code: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ScheduleError(f"Le champ {field} est obligatoire.", code)
        trimmed = value.strip()
        if len(trimmed) > max_length:
            raise ScheduleError(f"Le champ {field} est trop long.", code)
        return trimmed

    @staticmethod
    def _trim(error: str | None) -> str | None:
        if not error:
            return None
        text = str(error)
        return text[:300]

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

        return conn
