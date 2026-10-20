"""Machine-activity introspection: a live snapshot (CPU, memory, disk...) and
bucketed history for the charts panel, read from the local metrics store the
background sampler fills. All local, read-only.
"""

from __future__ import annotations

import time
from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.metrics.store import GAUGE_METRICS, MetricsStore
from jarvis.tools.system_metrics import SystemMetricsProbe

# Named periods -> lookback in seconds.
_PERIOD_SECONDS = {
    "1h": 3600, "6h": 6 * 3600, "12h": 12 * 3600,
    "24h": 24 * 3600, "today": 24 * 3600, "jour": 24 * 3600,
    "7d": 7 * 86400, "semaine": 7 * 86400, "week": 7 * 86400,
}

_METRIC_LABELS = {
    "cpu": "processeur", "mem": "mémoire", "disk": "disque",
    "swap": "swap", "load1": "charge", "battery": "batterie",
}

_METRIC_ALIASES = {
    "processeur": "cpu", "cpu": "cpu",
    "mémoire": "mem", "memoire": "mem", "memory": "mem", "ram": "mem", "mem": "mem",
    "disque": "disk", "disk": "disk", "swap": "swap",
    "charge": "load1", "load": "load1", "load1": "load1",
    "batterie": "battery", "battery": "battery",
}


def _gb(n: int | None) -> str:
    if not n:
        return "0 Go"
    return f"{n / 1e9:.1f} Go".replace(".", ",")


class SystemMetricsCapability:
    def __init__(self, probe: SystemMetricsProbe | None = None,
                 store: MetricsStore | None = None, clock=None):
        self.probe = probe if probe is not None else SystemMetricsProbe()
        self.store = store if store is not None else MetricsStore()
        self._clock = clock if clock is not None else time.time

    def _window(self, period: str) -> tuple[float, float, str]:
        now = self._clock()
        key = (period or "24h").strip().lower()
        seconds = _PERIOD_SECONDS.get(key, 24 * 3600)
        label = {3600: "la dernière heure", 24 * 3600: "sur 24 h",
                 7 * 86400: "sur 7 jours"}.get(seconds, f"sur {int(seconds/3600)} h")
        return now - seconds, now, label

    def _metric(self, name: str) -> str:
        return _METRIC_ALIASES.get((name or "cpu").strip().lower(), "cpu")

    def snapshot(self) -> ToolResult:
        if not self.probe.available():
            return ToolResult.failure("system_snapshot",
                                      "Les métriques machine sont indisponibles (psutil absent).",
                                      error_code="metrics_unavailable")
        try:
            s = self.probe.snapshot()
        except Exception as error:
            return ToolResult.failure("system_snapshot", f"Lecture impossible : {error}",
                                      error_code="metrics_unavailable")
        battery = ""
        if s.get("battery") is not None:
            plugged = "en charge" if s.get("power_plugged") else "sur batterie"
            battery = f", batterie {s['battery']:.0f} % ({plugged})"
        message = (
            f"Processeur {s['cpu']:.0f} %, mémoire {s['mem']:.0f} % "
            f"({_gb(s['mem_used'])} sur {_gb(s['mem_total'])}), "
            f"disque {s['disk']:.0f} %{battery}."
        )
        return ToolResult.success("system_snapshot", message, **s)

    def top_processes(self, by: str = "cpu", limit: int = 5) -> ToolResult:
        if not self.probe.available():
            return ToolResult.failure("top_processes",
                                      "Les métriques machine sont indisponibles (psutil absent).",
                                      error_code="metrics_unavailable")
        by = "cpu" if (by or "cpu").lower().startswith("c") else "memory"
        try:
            rows = self.probe.top_processes(by=by, limit=limit)
        except Exception as error:
            return ToolResult.failure("top_processes", f"Lecture impossible : {error}",
                                      error_code="metrics_unavailable")
        unit = "% CPU" if by == "cpu" else "% mémoire"
        names = ", ".join(f"{r['name']} {r['value']:g} {unit}" for r in rows[:4])
        kind = "processeur" if by == "cpu" else "mémoire"
        return ToolResult.success("top_processes",
                                  f"Processus les plus gourmands en {kind} : {names}.",
                                  by=by, processes=rows)

    def history(self, metric: str = "cpu", period: str = "24h") -> ToolResult:
        name = self._metric(metric)
        since, until, label = self._window(period)
        try:
            series = self.store.history(name, since=since, until=until)
            summary = self.store.summary(name, since=since, until=until)
        except Exception as error:
            return ToolResult.failure("system_usage_history", f"Lecture impossible : {error}",
                                      error_code="metrics_unavailable")
        human = _METRIC_LABELS.get(name, name)
        if not series:
            return ToolResult.success("system_usage_history",
                                      f"Pas encore d'historique {human} {label}. "
                                      "L'échantillonnage se remplit pendant que Jarvis tourne.",
                                      metric=name, period=label, series=[], summary=summary)
        message = (
            f"{human.capitalize()} {label} : moyenne {summary['avg']:g} %, "
            f"pic {summary['max']:g} % ({summary['samples']} relevés)."
        )
        return ToolResult.success("system_usage_history", message,
                                  metric=name, period=label, series=series, summary=summary)
