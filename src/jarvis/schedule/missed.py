"""Reminders delivered while no voice session was open.

A reminder that fell due while the Mac slept, or while Jarvis was closed, is
delivered by launchd as a notification that may never have been seen. At
the start of the next voice session, Jarvis says them in one sentence.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

MAX_ANNOUNCED = 5


def last_session_path() -> Path:
    return Path(os.environ.get("JARVIS_LAST_SESSION_PATH")
                or Path.home() / "Library/Application Support/Jarvis/last-voice-session")


def read_last_session_end(path: Path | None = None) -> float | None:
    try:
        return float((path or last_session_path()).read_text().strip())
    except (OSError, ValueError):
        return None


def record_session_end(now: float | None = None, path: Path | None = None) -> None:
    path = path or last_session_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{time.time() if now is None else now:.0f}\n")
    except OSError:
        pass  # Worst case: the same reminders are mentioned again next time.


def missed_reminders(store, since: float | None) -> list[dict]:
    """Reminders delivered after `since`, oldest first (none on a first run)."""
    if since is None:
        return []
    rows = [row for row in store.list("done", limit=200) if (row.get("done_at") or 0) > since]
    rows.sort(key=lambda row: row.get("done_at") or 0)
    return rows[-MAX_ANNOUNCED:]


def missed_announcement(rows: list[dict]) -> str | None:
    if not rows:
        return None
    parts = []
    for row in rows:
        when = datetime.fromtimestamp(row["due_at"]).strftime("%d/%m a %H:%M")
        text = " ".join(str(row.get("text", "")).split())[:120]
        parts.append(f"« {text} » ({when})")
    return ("Annonce brievement, en une seule phrase, que pendant ton absence ces rappels "
            "ont ete delivres en notification : " + " ; ".join(parts) + ". "
            "Ne lance aucune action et n'en recree aucun.")
