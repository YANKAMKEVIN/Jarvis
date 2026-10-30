"""Local, private index of Claude Code token usage (SQLite).

Jarvis reads the user's own Claude Code transcripts under ~/.claude/projects to
report how many tokens have been spent, by day, model and project -- entirely
offline, no API, no key. Only usage *metadata* is indexed: token counts, model
name, timestamp and the project folder name. Message content, prompts, tool
results and file paths are never read into the database.

Transcripts are append-only JSONL, one message per line. Ingestion is
incremental: each file is remembered by size and the byte offset parsed so far,
so re-indexing only reads newly appended lines. A cold first pass over a few GB
takes a handful of seconds; subsequent passes are near-instant.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable

# Only lines that contain this token carry a usage block; checking the raw bytes
# first lets us skip the ~75% of lines (user turns, tool results) cheaply.
_USAGE_MARKER = b'"usage"'

# Approximate Anthropic API list prices in USD per million tokens, by model
# family. Subscription (Claude Code) users do NOT pay these -- the figure is an
# "API-equivalent" estimate, surfaced as such. Keys are matched as substrings of
# the model id, most specific first.
_PRICES: tuple[tuple[str, dict[str, float]], ...] = (
    ("opus", {"input": 15.0, "output": 75.0, "cache_create": 18.75, "cache_read": 1.5}),
    ("sonnet", {"input": 3.0, "output": 15.0, "cache_create": 3.75, "cache_read": 0.3}),
    ("haiku", {"input": 0.8, "output": 4.0, "cache_create": 1.0, "cache_read": 0.08}),
    ("fable", {"input": 0.8, "output": 4.0, "cache_create": 1.0, "cache_read": 0.08}),
)
_DEFAULT_PRICE = {"input": 3.0, "output": 15.0, "cache_create": 3.75, "cache_read": 0.3}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    uuid TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    day TEXT NOT NULL,
    model TEXT NOT NULL,
    project TEXT NOT NULL,
    session TEXT,
    input INTEGER NOT NULL,
    output INTEGER NOT NULL,
    cache_create INTEGER NOT NULL,
    cache_read INTEGER NOT NULL,
    thinking INTEGER NOT NULL,
    web_search INTEGER NOT NULL,
    web_fetch INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_day ON usage_events(day);
CREATE INDEX IF NOT EXISTS usage_ts ON usage_events(ts);
CREATE INDEX IF NOT EXISTS usage_model ON usage_events(model);

-- One row per transcript file, so re-ingestion only reads new bytes.
CREATE TABLE IF NOT EXISTS ingested (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    offset INTEGER NOT NULL
);
"""

# Order matters for row -> tuple binding below.
_COLUMNS = (
    "uuid", "ts", "day", "model", "project", "session",
    "input", "output", "cache_create", "cache_read",
    "thinking", "web_search", "web_fetch",
)

_TOKEN_FIELDS = ("input", "output", "cache_create", "cache_read")

# Bumped whenever project_label changes, so stored labels get recomputed.
_LABEL_VERSION = 1


def default_usage_db_path() -> Path:
    override = os.environ.get("JARVIS_USAGE_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Jarvis" / "usage.db"


def default_projects_dir() -> Path:
    override = os.environ.get("JARVIS_CLAUDE_PROJECTS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "projects"


def model_family(model: str) -> str:
    low = (model or "").lower()
    for family, _ in _PRICES:
        if family in low:
            return family
    return "autre"


def estimate_cost(tokens: dict[str, float], model: str) -> float:
    """API-equivalent USD estimate for one bundle of token counts."""
    prices = _DEFAULT_PRICE
    low = (model or "").lower()
    for family, table in _PRICES:
        if family in low:
            prices = table
            break
    return sum(tokens.get(field, 0) * prices[field] / 1_000_000 for field in _TOKEN_FIELDS)


def decode_project(folder: str) -> str:
    """`-Users-kevinyankam-dev-Jarvis` -> `/Users/kevinyankam/dev/Jarvis`."""
    return folder.replace("-", "/") if folder.startswith("-") else folder


def _resolve_folder(folder: str, root: Path) -> tuple[Path, bool]:
    """Walk the real filesystem to undo Claude's lossy folder encoding, where
    '/', '.', ' ' and '-' all became '-'. Returns the deepest existing
    directory and whether the whole name resolved."""
    tokens = folder[1:].split("-")
    current, i = root, 0
    while i < len(tokens):
        for j in range(len(tokens), i, -1):
            parts = tokens[i:j]
            dot = parts[0] == "" and len(parts) > 1
            words = parts[1:] if dot else parts
            names = sorted({("." if dot else "") + sep.join(words) for sep in ("-", " ")})
            match = next((current / n for n in names if (current / n).is_dir()), None)
            if match is not None:
                current, i = match, j
                break
        else:
            return current, False
    return current, True


@lru_cache(maxsize=512)
def project_label(folder: str, root: str = "/", home: str | None = None) -> str:
    """`-Users-me-dev-kanto-2026` -> `kanto-2026`. Worktrees and sibling
    checkouts (`kanto-2026--claude-worktrees-x`, `kanto-2026-wt-s2a`) fold into
    their project, as long as the project folder still exists on disk."""
    decoded = decode_project(folder).rstrip("/")
    naive = decoded.rsplit("/", 1)[-1] or decoded or folder
    if not folder.startswith("-"):
        return naive
    base = Path(root)
    resolved, complete = _resolve_folder(folder, base)
    text = str(resolved)
    if "/.claude/worktrees" in text:
        resolved = Path(text.split("/.claude/worktrees", 1)[0])
        complete = True
    # A partial match that stops at the home folder or one of its direct
    # children ("dev", "Documents") says nothing about the project: the folder
    # was deleted, so keep the old last-segment guess.
    home_path = Path(home) if home is not None else base / Path.home().relative_to("/")
    if resolved == base or (not complete and len(resolved.parts) <= len(home_path.parts) + 1):
        return naive
    return resolved.name or naive


def _parse_ts(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        text = iso.replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except (ValueError, TypeError):
        return None


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _parse_line(raw: bytes, folder: str) -> tuple | None:
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if record.get("type") != "assistant":
        return None
    message = record.get("message") or {}
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    model = message.get("model") or "?"
    if model == "<synthetic>":  # injected placeholder, no real API call
        return None
    uuid = record.get("uuid")
    ts = _parse_ts(record.get("timestamp"))
    if not uuid or ts is None:
        return None
    server = usage.get("server_tool_use") or {}
    day = time.strftime("%Y-%m-%d", time.localtime(ts))
    return (
        uuid, ts, day, model, project_label(folder), record.get("sessionId"),
        _as_int(usage.get("input_tokens")),
        _as_int(usage.get("output_tokens")),
        _as_int(usage.get("cache_creation_input_tokens")),
        _as_int(usage.get("cache_read_input_tokens")),
        _as_int((usage.get("output_tokens_details") or {}).get("thinking_tokens")),
        _as_int(server.get("web_search_requests")),
        _as_int(server.get("web_fetch_requests")),
    )


@dataclass(frozen=True)
class IngestResult:
    files_scanned: int
    files_read: int
    new_events: int
    elapsed: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_scanned": self.files_scanned,
            "files_read": self.files_read,
            "new_events": self.new_events,
            "elapsed_seconds": round(self.elapsed, 2),
        }


class UsageStore:
    def __init__(
        self,
        db_path: str | Path | None = None,
        projects_dir: str | Path | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._db_path = Path(db_path).expanduser() if db_path is not None else None
        self._projects = Path(projects_dir).expanduser() if projects_dir is not None else None
        self._clock = clock if clock is not None else time.time
        self._initialized_path: Path | None = None

    @property
    def path(self) -> Path:
        return self._db_path if self._db_path is not None else default_usage_db_path()

    @property
    def projects_dir(self) -> Path:
        return self._projects if self._projects is not None else default_projects_dir()

    # --- ingestion ----------------------------------------------------------

    def ingest(self) -> IngestResult:
        start = time.time()
        conn = self._connect()
        files = sorted(self.projects_dir.glob("*/*.jsonl")) if self.projects_dir.exists() else []
        read = new = 0
        try:
            for path in files:
                added = self._ingest_file(conn, path)
                if added is not None:
                    read += 1
                    new += added
            conn.commit()
        finally:
            conn.close()
        return IngestResult(len(files), read, new, time.time() - start)

    def _ingest_file(self, conn: sqlite3.Connection, path: Path) -> int | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        row = conn.execute(
            "SELECT size, offset FROM ingested WHERE path = ?", (str(path),)
        ).fetchone()
        offset = 0
        if row is not None:
            if row["size"] == stat.st_size:
                return None  # unchanged append-only log
            # Grew -> resume from offset; shrank/rotated -> reparse from start.
            offset = row["offset"] if stat.st_size > row["size"] else 0

        folder = path.parent.name
        batch: list[tuple] = []
        consumed = offset
        try:
            with path.open("rb") as handle:
                handle.seek(offset)
                for raw in handle:
                    if not raw.endswith(b"\n"):
                        break  # partial final line: leave it for next time
                    consumed += len(raw)
                    if _USAGE_MARKER in raw:
                        event = _parse_line(raw, folder)
                        if event is not None:
                            batch.append(event)
        except OSError:
            return None

        before = conn.total_changes
        if batch:
            conn.executemany(
                f"INSERT OR IGNORE INTO usage_events ({','.join(_COLUMNS)}) "
                f"VALUES ({','.join('?' for _ in _COLUMNS)})",
                batch,
            )
        added = conn.total_changes - before
        conn.execute(
            "INSERT OR REPLACE INTO ingested (path, size, mtime, offset) VALUES (?, ?, ?, ?)",
            (str(path), stat.st_size, stat.st_mtime, consumed),
        )
        return added

    # --- queries ------------------------------------------------------------

    def totals(self, since: float | None = None, until: float | None = None) -> dict[str, Any]:
        conn = self._connect()
        try:
            where, params = self._window(since, until)
            row = conn.execute(
                "SELECT COUNT(*) n, "
                "COALESCE(SUM(input),0) input, COALESCE(SUM(output),0) output, "
                "COALESCE(SUM(cache_create),0) cache_create, "
                "COALESCE(SUM(cache_read),0) cache_read, "
                "COALESCE(SUM(thinking),0) thinking, "
                "COALESCE(SUM(web_search),0) web_search, "
                "COALESCE(SUM(web_fetch),0) web_fetch, "
                "COUNT(DISTINCT day) days, COUNT(DISTINCT session) sessions "
                f"FROM usage_events{where}",
                params,
            ).fetchone()
            return self._summary(dict(row))
        finally:
            conn.close()

    def by_model(self, since: float | None = None, until: float | None = None) -> list[dict[str, Any]]:
        return self._grouped("model", since, until)

    def by_project(self, since: float | None = None, until: float | None = None) -> list[dict[str, Any]]:
        return self._grouped("project", since, until)

    def by_day(self, days: int = 30, until: float | None = None) -> list[dict[str, Any]]:
        end = until if until is not None else self._clock()
        start = end - days * 86400
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT day, "
                "SUM(input) input, SUM(output) output, "
                "SUM(cache_create) cache_create, SUM(cache_read) cache_read, "
                "SUM(thinking) thinking, COUNT(*) n "
                "FROM usage_events WHERE ts >= ? AND ts <= ? "
                "GROUP BY day ORDER BY day",
                (start, end),
            ).fetchall()
            return [self._row_summary(dict(r), key="day") for r in rows]
        finally:
            conn.close()

    def _grouped(self, column: str, since: float | None, until: float | None) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            where, params = self._window(since, until)
            rows = conn.execute(
                f"SELECT {column} AS key, "
                "SUM(input) input, SUM(output) output, "
                "SUM(cache_create) cache_create, SUM(cache_read) cache_read, "
                "SUM(thinking) thinking, COUNT(*) n "
                f"FROM usage_events{where} GROUP BY {column} "
                "ORDER BY (SUM(input)+SUM(output)+SUM(cache_create)+SUM(cache_read)) DESC",
                params,
            ).fetchall()
            return [self._row_summary(dict(r), key="key", model_hint=column) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _window(since: float | None, until: float | None) -> tuple[str, list[Any]]:
        clauses, params = [], []
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if until is not None:
            clauses.append("ts <= ?")
            params.append(until)
        return (f" WHERE {' AND '.join(clauses)}" if clauses else "", params)

    def _summary(self, row: dict[str, Any]) -> dict[str, Any]:
        tokens = {f: int(row.get(f, 0) or 0) for f in _TOKEN_FIELDS}
        total = sum(tokens.values())
        return {
            "events": int(row.get("n", 0) or 0),
            "days": int(row.get("days", 0) or 0),
            "sessions": int(row.get("sessions", 0) or 0),
            "input": tokens["input"],
            "output": tokens["output"],
            "cache_create": tokens["cache_create"],
            "cache_read": tokens["cache_read"],
            "thinking": int(row.get("thinking", 0) or 0),
            "web_search": int(row.get("web_search", 0) or 0),
            "web_fetch": int(row.get("web_fetch", 0) or 0),
            "total_tokens": total,
        }

    def _row_summary(self, row: dict[str, Any], key: str, model_hint: str | None = None) -> dict[str, Any]:
        tokens = {f: int(row.get(f, 0) or 0) for f in _TOKEN_FIELDS}
        total = sum(tokens.values())
        label = row.get(key)
        out = {
            key if key != "key" else (model_hint or "key"): label,
            "events": int(row.get("n", 0) or 0),
            "input": tokens["input"],
            "output": tokens["output"],
            "cache_create": tokens["cache_create"],
            "cache_read": tokens["cache_read"],
            "thinking": int(row.get("thinking", 0) or 0),
            "total_tokens": total,
        }
        if model_hint == "model":
            out["est_cost_usd"] = round(estimate_cost(tokens, str(label)), 4)
        return out

    def recent_sessions(self, limit: int = 10, since: float | None = None) -> list[dict[str, Any]]:
        """Most recent Claude Code sessions with per-session tokens and cost."""
        conn = self._connect()
        try:
            where, params = self._window(since, None)
            clause = (where + " AND session IS NOT NULL") if where else " WHERE session IS NOT NULL"
            rows = conn.execute(
                "SELECT session, model, project, "
                "SUM(input) input, SUM(output) output, "
                "SUM(cache_create) cache_create, SUM(cache_read) cache_read, "
                "COUNT(*) n, MIN(ts) first_ts, MAX(ts) last_ts "
                f"FROM usage_events{clause} GROUP BY session, model, project",
                params,
            ).fetchall()
        finally:
            conn.close()

        sessions: dict[str, dict[str, Any]] = {}
        for row in rows:
            data = sessions.setdefault(row["session"], {
                "session": row["session"], "events": 0, "total_tokens": 0,
                "est_cost_usd": 0.0, "first_ts": row["first_ts"], "last_ts": row["last_ts"],
                "models": set(), "projects": {},
            })
            tokens = {f: int(row[f] or 0) for f in _TOKEN_FIELDS}
            data["events"] += int(row["n"] or 0)
            data["total_tokens"] += sum(tokens.values())
            data["est_cost_usd"] += estimate_cost(tokens, row["model"])
            data["models"].add(row["model"])
            data["first_ts"] = min(data["first_ts"], row["first_ts"])
            data["last_ts"] = max(data["last_ts"], row["last_ts"])
            data["projects"][row["project"]] = data["projects"].get(row["project"], 0) + int(row["n"] or 0)

        out = []
        for data in sessions.values():
            project = max(data["projects"], key=data["projects"].get) if data["projects"] else ""
            out.append({
                "session": data["session"],
                "project": project,
                "models": sorted(data["models"]),
                "events": data["events"],
                "total_tokens": data["total_tokens"],
                "est_cost_usd": round(data["est_cost_usd"], 4),
                "first_ts": data["first_ts"],
                "last_ts": data["last_ts"],
                "duration_min": round((data["last_ts"] - data["first_ts"]) / 60, 1),
            })
        out.sort(key=lambda s: s["last_ts"], reverse=True)
        return out[: max(1, min(int(limit) if isinstance(limit, (int, float)) else 10, 50))]

    def clear(self) -> None:
        """Drop the whole index (both events and the ingestion cursor)."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM usage_events")
            conn.execute("DELETE FROM ingested")
            conn.commit()
        finally:
            conn.close()

    # --- connection ---------------------------------------------------------

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
            if conn.execute("PRAGMA user_version").fetchone()[0] < _LABEL_VERSION:
                # Project labels are computed at ingest; a better labeller
                # means re-reading the transcripts once.
                conn.execute("DELETE FROM usage_events")
                conn.execute("DELETE FROM ingested")
                conn.execute(f"PRAGMA user_version = {_LABEL_VERSION}")
                conn.commit()
            self._initialized_path = path
        return conn
