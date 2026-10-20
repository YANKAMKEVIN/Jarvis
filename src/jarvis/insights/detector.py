"""Anomaly detection over the local introspection stores.

Explainable rules, no model: a sustained CPU or memory load over the last few
minutes of sampler history, a nearly full disk, and a day of Claude Code token
consumption far above the user's own recent norm. The detector is stateless
(each `scan` reports what is abnormal right now); `InsightMonitor` adds the
per-kind cooldown so a lasting condition is announced once, not every tick.
Everything is read locally; nothing leaves the machine.
"""

from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from jarvis.metrics.store import MetricsStore


@dataclass(frozen=True)
class Thresholds:
    window_seconds: float = 5 * 60
    min_samples: int = 6            # ~2 min of 20 s samples before judging a load
    cpu_percent: float = 85.0
    mem_percent: float = 90.0
    disk_percent: float = 90.0
    token_ratio: float = 2.0        # today vs median of past active days
    token_floor: int = 5_000_000    # ignore spikes on small absolute volumes
    token_min_days: int = 5         # history needed before a baseline is trusted
    token_lookback_days: int = 14


@dataclass(frozen=True)
class Insight:
    kind: str
    severity: str                   # "warning" or "info"
    title: str
    message: str
    ts: float
    key: str = ""                   # cooldown identity (defaults to kind)
    once: bool = False              # fire once per key, never again (day-scoped keys)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _gb(n: int | float | None) -> str:
    return f"{(n or 0) / 1e9:.0f} Go"


def _human(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f} Md".replace(".", ",")
    if n >= 1_000_000:
        return f"{n / 1e6:.1f} M".replace(".", ",")
    return f"{n / 1e3:.0f} k"


class InsightDetector:
    def __init__(self, metrics: MetricsStore | None = None, usage=None, probe=None,
                 thresholds: Thresholds | None = None,
                 clock: Callable[[], float] | None = None):
        self.metrics = metrics if metrics is not None else MetricsStore()
        self.usage = usage          # UsageStore, optional (token rule skipped without it)
        self.probe = probe          # SystemMetricsProbe, optional (names the culprit)
        self.t = thresholds if thresholds is not None else Thresholds()
        self._clock = clock if clock is not None else time.time

    def scan(self, include_tokens: bool = True) -> list[Insight]:
        found = self.machine_insights()
        if include_tokens:
            found += self.token_insights()
        return found

    # --- machine ------------------------------------------------------------

    def machine_insights(self) -> list[Insight]:
        now = self._clock()
        since = now - self.t.window_seconds
        out: list[Insight] = []
        cpu = self.metrics.summary("cpu", since=since, until=now)
        if cpu["samples"] >= self.t.min_samples and cpu["avg"] >= self.t.cpu_percent:
            culprit = self._top("cpu")
            tail = f" Le plus gourmand : {culprit['name']}." if culprit else ""
            out.append(Insight(
                "cpu_sustained", "warning", "Processeur saturé",
                f"Le processeur tourne à {cpu['avg']:.0f} % en moyenne depuis "
                f"{self.t.window_seconds / 60:.0f} minutes.{tail}",
                now, data={"avg": cpu["avg"], "top_process": culprit}))
        mem = self.metrics.summary("mem", since=since, until=now)
        if mem["samples"] >= self.t.min_samples and mem["avg"] >= self.t.mem_percent:
            culprit = self._top("memory")
            tail = f" Le plus gourmand : {culprit['name']}." if culprit else ""
            out.append(Insight(
                "mem_pressure", "warning", "Mémoire presque pleine",
                f"La mémoire est occupée à {mem['avg']:.0f} % depuis "
                f"{self.t.window_seconds / 60:.0f} minutes.{tail}",
                now, data={"avg": mem["avg"], "top_process": culprit}))
        latest = self.metrics.latest()
        if latest and latest.get("disk") is not None and latest["ts"] >= since \
                and latest["disk"] >= self.t.disk_percent:
            free = (latest.get("disk_total") or 0) - (latest.get("disk_used") or 0)
            out.append(Insight(
                "disk_full", "warning", "Disque presque plein",
                f"Le disque est rempli à {latest['disk']:.0f} %, il reste {_gb(free)}.",
                now, data={"percent": latest["disk"], "free_bytes": free}))
        return out

    def _top(self, by: str) -> dict | None:
        if self.probe is None:
            return None
        try:
            rows = self.probe.top_processes(by=by, limit=1)
        except Exception:
            return None
        return rows[0] if rows else None

    # --- tokens -------------------------------------------------------------

    def token_insights(self) -> list[Insight]:
        if self.usage is None:
            return []
        now = self._clock()
        try:
            self.usage.ingest()
        except Exception:
            pass
        try:
            days = self.usage.by_day(days=self.t.token_lookback_days + 1, until=now)
        except Exception:
            return []
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        current = next((d["total_tokens"] for d in days if d["day"] == today), 0)
        past = [d["total_tokens"] for d in days if d["day"] != today and d["total_tokens"] > 0]
        if len(past) < self.t.token_min_days or current < self.t.token_floor:
            return []
        baseline = statistics.median(past)
        if baseline <= 0 or current < self.t.token_ratio * baseline:
            return []
        ratio = current / baseline
        return [Insight(
            "token_day_spike", "info", "Consommation de tokens inhabituelle",
            f"Aujourd'hui : {_human(current)} tokens, soit {ratio:.1f}".replace(".", ",")
            + f" fois votre journée type ({_human(int(baseline))}).",
            now, key=f"token_day_spike:{today}", once=True,
            data={"today": current, "baseline": int(baseline), "ratio": round(ratio, 2)})]


class InsightMonitor:
    """Runs the detector periodically and fires each condition once per cooldown.

    Qt-free: the desktop drives `tick()` from a timer (off the GUI thread) and
    passes a `notifier` that hands each new insight back to the GUI.
    """

    def __init__(self, detector: InsightDetector,
                 notifier: Callable[[Insight], None] | None = None,
                 cooldown_seconds: float = 3600.0, token_every_seconds: float = 1800.0,
                 clock: Callable[[], float] | None = None):
        self.detector = detector
        self.notifier = notifier
        self.cooldown = cooldown_seconds
        self.token_every = token_every_seconds
        self._clock = clock if clock is not None else time.time
        self._last_fired: dict[str, float] = {}
        self._last_token_check: float | None = None
        self._recent: deque[Insight] = deque(maxlen=20)
        self._lock = threading.Lock()

    def tick(self) -> list[Insight]:
        if not self._lock.acquire(blocking=False):
            return []  # a previous tick (slow token ingest) is still running
        try:
            now = self._clock()
            check_tokens = (self._last_token_check is None
                            or now - self._last_token_check >= self.token_every)
            if check_tokens:
                self._last_token_check = now
            try:
                found = self.detector.scan(include_tokens=check_tokens)
            except Exception:
                return []
            fresh = []
            for insight in found:
                key = insight.key or insight.kind
                last = self._last_fired.get(key)
                if last is not None and (insight.once or now - last < self.cooldown):
                    continue
                self._last_fired[key] = now
                self._recent.append(insight)
                fresh.append(insight)
            for insight in fresh:
                if self.notifier is not None:
                    try:
                        self.notifier(insight)
                    except Exception:
                        pass
            return fresh
        finally:
            self._lock.release()

    def recent(self, limit: int = 10) -> list[Insight]:
        return list(self._recent)[-max(1, int(limit)):][::-1]
