"""Local SQLite history of machine metrics.

A lightweight ring of samples (CPU %, memory %, disk %, load, battery, and
cumulative network counters) written by the background sampler. Gauge metrics
are read back bucketed (averaged per time bucket) so charts stay smooth whatever
the sample rate. Everything is local and private; the file is 0600.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

METRICS_RETENTION_SECONDS = 14 * 24 * 3600

# Gauge metrics that can be averaged directly over a time bucket.
GAUGE_METRICS = ("cpu", "mem", "disk", "swap", "load1", "battery")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts REAL PRIMARY KEY,
    cpu REAL, mem REAL, mem_used INTEGER, mem_total INTEGER,
    swap REAL, disk REAL, disk_used INTEGER, disk_total INTEGER,
    net_sent INTEGER, net_recv INTEGER,
    load1 REAL, battery REAL
);
CREATE INDEX IF NOT EXISTS samples_ts ON samples(ts);
"""

_COLUMNS = (
    "ts", "cpu", "mem", "mem_used", "mem_total", "swap", "disk",
    "disk_used", "disk_total", "net_sent", "net_recv", "load1", "battery",
)


def default_metrics_db_path() -> Path:
    override = os.environ.get("JARVIS_METRICS_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Jarvis" / "metrics.db"


class MetricsStore:
    def __init__(self, db_path: str | Path | None = None, clock: Callable[[], float] | None = None):
        self._db_path = Path(db_path).expanduser() if db_path is not None else None
        self._clock = clock if clock is not None else time.time
        self._initialized_path: Path | None = None

    @property
    def path(self) -> Path:
        return self._db_path if self._db_path is not None else default_metrics_db_path()

    def record(self, sample: dict[str, Any]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO samples ({','.join(_COLUMNS)}) "
                f"VALUES ({','.join('?' for _ in _COLUMNS)})",
                tuple(sample.get(col) for col in _COLUMNS),
            )
            conn.commit()
        finally:
            conn.close()

    def latest(self) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM samples ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._connect()
        try:
            return int(conn.execute("SELECT COUNT(*) n FROM samples").fetchone()["n"])
        finally:
            conn.close()

    def history(self, metric: str = "cpu", since: float | None = None,
                until: float | None = None, buckets: int = 48) -> list[dict[str, Any]]:
        """Bucketed average series for a gauge metric, oldest first."""
        if metric not in GAUGE_METRICS:
            raise ValueError(f"metric inconnu: {metric}")
        now = self._clock()
        end = until if until is not None else now
        start = since if since is not None else end - 24 * 3600
        span = max(end - start, 1.0)
        bucket = span / max(1, int(buckets))
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT CAST((ts - ?) / ? AS INTEGER) AS b, "
                f"AVG({metric}) AS value, MIN(ts) AS ts "
                "FROM samples WHERE ts >= ? AND ts <= ? AND "
                f"{metric} IS NOT NULL GROUP BY b ORDER BY b",
                (start, bucket, start, end),
            ).fetchall()
            return [{"ts": r["ts"], "value": round(r["value"], 1)} for r in rows]
        finally:
            conn.close()

    def summary(self, metric: str = "cpu", since: float | None = None,
                until: float | None = None) -> dict[str, Any]:
        if metric not in GAUGE_METRICS:
            raise ValueError(f"metric inconnu: {metric}")
        now = self._clock()
        end = until if until is not None else now
        start = since if since is not None else end - 24 * 3600
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT COUNT({metric}) n, AVG({metric}) avg, "
                f"MAX({metric}) max, MIN({metric}) min "
                f"FROM samples WHERE ts >= ? AND ts <= ? AND {metric} IS NOT NULL",
                (start, end),
            ).fetchone()
            n = int(row["n"] or 0)
            return {
                "metric": metric, "samples": n,
                "avg": round(row["avg"], 1) if n else None,
                "max": round(row["max"], 1) if n else None,
                "min": round(row["min"], 1) if n else None,
            }
        finally:
            conn.close()

    def clear(self) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM samples")
            conn.commit()
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
        conn.execute("DELETE FROM samples WHERE ts <= ?",
                     (self._clock() - METRICS_RETENTION_SECONDS,))
        return conn
