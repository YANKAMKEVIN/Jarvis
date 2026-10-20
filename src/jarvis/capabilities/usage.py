"""Token-usage introspection: how many tokens Claude Code has spent, read from
the user's own local transcripts. No network, no API key -- the UsageStore
indexes ~/.claude/projects locally and this capability shapes the aggregates
into voice-friendly ToolResults plus structured series for the charts panel.
"""

from __future__ import annotations

import time
from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.usage.store import UsageStore, estimate_cost

# Named periods the user can ask for by voice, resolved to a lookback in days
# (None = all history). Day-boundary periods ("today"/"yesterday") are handled
# apart so "aujourd'hui" means since local midnight, not the last 24h.
_PERIOD_DAYS = {
    "7d": 7, "semaine": 7, "week": 7,
    "30d": 30, "mois": 30, "month": 30,
    "90d": 90, "trimestre": 90,
    "all": None, "tout": None, "total": None,
}


def _human(n: int) -> str:
    """Compact French token count: 28_800_000 -> '28,8 M'."""
    n = int(n)
    if abs(n) >= 1_000_000_000:
        return f"{n / 1e9:.1f} Md".replace(".", ",")
    if abs(n) >= 1_000_000:
        return f"{n / 1e6:.1f} M".replace(".", ",")
    if abs(n) >= 1_000:
        return f"{n / 1e3:.0f} k"
    return str(n)


class UsageCapability:
    def __init__(self, store: UsageStore | None = None, clock=None):
        self.store = store if store is not None else UsageStore()
        self._clock = clock if clock is not None else time.time

    # --- period helpers -----------------------------------------------------

    def _window(self, period: str) -> tuple[float | None, float | None, str]:
        now = self._clock()
        key = (period or "7d").strip().lower()
        if key in ("today", "aujourd'hui", "jour"):
            return self._midnight(now), now, "aujourd'hui"
        if key in ("yesterday", "hier"):
            start = self._midnight(now)
            return start - 86400, start, "hier"
        if key in _PERIOD_DAYS:
            days = _PERIOD_DAYS[key]
            if days is None:
                return None, now, "depuis le début"
            return now - days * 86400, now, f"sur {days} jours"
        # Unknown -> default to a week.
        return now - 7 * 86400, now, "sur 7 jours"

    @staticmethod
    def _midnight(ts: float) -> float:
        lt = time.localtime(ts)
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))

    def _fresh(self) -> None:
        # Cheap after the first pass (reads only newly appended lines). Never
        # lets an indexing hiccup break a read.
        try:
            self.store.ingest()
        except Exception:
            pass

    # --- tools --------------------------------------------------------------

    def overview(self, period: str = "7d") -> ToolResult:
        self._fresh()
        since, until, label = self._window(period)
        try:
            t = self.store.totals(since, until)
        except Exception as error:
            return ToolResult.failure("token_usage", f"Lecture de l'usage impossible : {error}",
                                      error_code="usage_unavailable")
        if t["events"] == 0:
            return ToolResult.success("token_usage",
                                      f"Aucune activité Claude enregistrée {label}.",
                                      period=label, **t)
        message = (
            f"{label.capitalize()} : {_human(t['output'])} tokens générés, "
            f"{_human(t['input'])} en entrée, {_human(t['cache_read'])} lus en cache, "
            f"sur {t['sessions']} session(s)."
        )
        return ToolResult.success("token_usage", message, period=label, **t)

    def by_model(self, period: str = "30d") -> ToolResult:
        self._fresh()
        since, until, label = self._window(period)
        rows = self.store.by_model(since, until)
        if not rows:
            return ToolResult.success("token_usage_by_model",
                                      f"Aucune activité {label}.", period=label, models=[])
        top = rows[0]
        message = f"{label.capitalize()}, par modèle : " + ", ".join(
            f"{r['model'].replace('claude-', '')} {_human(r['total_tokens'])}" for r in rows[:4]
        ) + "."
        return ToolResult.success("token_usage_by_model", message,
                                  period=label, models=rows, top_model=top["model"])

    def by_project(self, period: str = "30d", limit: int = 5) -> ToolResult:
        self._fresh()
        since, until, label = self._window(period)
        rows = self.store.by_project(since, until)
        limit = max(1, min(int(limit) if isinstance(limit, (int, float)) else 5, 20))
        shown = rows[:limit]
        if not shown:
            return ToolResult.success("token_usage_by_project",
                                      f"Aucune activité {label}.", period=label, projects=[])
        message = f"{label.capitalize()}, top projets : " + ", ".join(
            f"{r['project']} {_human(r['total_tokens'])}" for r in shown
        ) + "."
        return ToolResult.success("token_usage_by_project", message,
                                  period=label, projects=shown)

    def trend(self, days: int = 14) -> ToolResult:
        self._fresh()
        days = max(2, min(int(days) if isinstance(days, (int, float)) else 14, 120))
        series = self.store.by_day(days=days)
        if not series:
            return ToolResult.success("token_usage_trend", "Pas encore d'historique.",
                                      days=days, series=[])
        busiest = max(series, key=lambda d: d["total_tokens"])
        message = (
            f"Sur {days} jours : pic le {busiest['day']} "
            f"({_human(busiest['total_tokens'])} tokens)."
        )
        return ToolResult.success("token_usage_trend", message, days=days, series=series)

    def recent_sessions(self, limit: int = 5) -> ToolResult:
        self._fresh()
        rows = self.store.recent_sessions(limit=limit)
        if not rows:
            return ToolResult.success("recent_claude_sessions",
                                      "Aucune session Claude enregistrée.", sessions=[])
        parts = []
        for s in rows[:3]:
            when = time.strftime("%d/%m", time.localtime(s["last_ts"]))
            project = s["project"] or "projet inconnu"
            parts.append(f"{project} le {when}, {_human(s['total_tokens'])} tokens")
        message = "Dernières sessions Claude : " + " ; ".join(parts) + "."
        return ToolResult.success("recent_claude_sessions", message, sessions=rows)

    def compare(self, period: str = "7d") -> ToolResult:
        """Compare a period with the equal-length window just before it."""
        self._fresh()
        key = (period or "7d").strip().lower()
        days = _PERIOD_DAYS.get(key, 7) or 7
        now = self._clock()
        cur = self.store.totals(now - days * 86400, now)
        prev = self.store.totals(now - 2 * days * 86400, now - days * 86400)
        cur_t, prev_t = cur["total_tokens"], prev["total_tokens"]
        if prev_t == 0:
            delta_txt = "aucune donnée sur la période précédente"
        else:
            pct = (cur_t - prev_t) / prev_t * 100
            arrow = "en hausse" if pct >= 0 else "en baisse"
            delta_txt = f"{arrow} de {abs(pct):.0f} %"
        message = (
            f"Sur {days} jours : {_human(cur_t)} tokens, "
            f"contre {_human(prev_t)} les {days} jours d'avant — {delta_txt}."
        )
        return ToolResult.success("compare_token_usage", message,
                                  days=days, current=cur, previous=prev)
