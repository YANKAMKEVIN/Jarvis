"""Palette, periods and pure formatting helpers of the introspection charts."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Sequence


# Shared palette, aligned with the desktop dark theme.
_BG = "#0b111b"
_PANEL = "#121d2b"
_TEXT = "#dce8f6"
_MUTED = "#93a7bc"
_UP = "#f6c177"     # more tokens than before: worth a look, not an error
_DOWN = "#8af0e0"
_ALERT = "#f0a7ba"
_TODAY = "#e6f4ff"  # the current day or week in the token chart
_PEAK = _UP
_ACCENTS = ["#82caff", "#8af0e0", "#bea5ff", "#f0a7ba", "#9ad0ea", "#f6c177"]

# Period presets offered by each dashboard's selector.
USAGE_PERIODS = (("today", "Aujourd'hui"), ("7d", "7 j"), ("30d", "30 j"), ("all", "Tout"))
METRIC_PERIODS = (("1h", "1 h"), ("6h", "6 h"), ("24h", "24 h"), ("7d", "7 j"))

# Days shown in the daily chart for each usage period. "Aujourd'hui" keeps a
# week of context, otherwise the chart would be a single bar.
TREND_DAYS = {"today": 7, "7d": 7, "30d": 30, "all": 120}

# Past this many days the daily chart groups by week to stay readable.
_WEEKLY_AFTER = 31

# How often the machine dashboard re-reads its data while it is visible.
METRICS_REFRESH_MS = 30_000

_UNITS = ((1e9, "Md"), (1e6, "M"), (1e3, "k"))

_MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre")


def _short_day(day: str) -> str:
    # '2026-10-16' -> '16/10'
    try:
        _, m, d = day.split("-")
        return f"{d}/{m}"
    except ValueError:
        return day


def _millions(n: float) -> float:
    return round(n / 1_000_000, 2)


def _unit(values: Sequence[float]) -> tuple[float, str]:
    """Pick the divisor and suffix that keep the largest value under 1000."""
    top = max((abs(v) for v in values), default=0)
    for divisor, suffix in _UNITS:
        if top >= divisor:
            return divisor, suffix
    return 1.0, ""


def fill_days(series: Sequence[dict[str, Any]], days: int,
              today: dt.date | None = None) -> list[dict[str, Any]]:
    """One entry per calendar day over the last `days` days, zero where the
    store has no row, so idle days show as gaps instead of vanishing."""
    end = today or dt.date.today()
    by_day = {row["day"]: row.get("total_tokens", 0) for row in series}
    out = []
    for offset in range(days - 1, -1, -1):
        day = (end - dt.timedelta(days=offset)).isoformat()
        out.append({"day": day, "total_tokens": by_day.get(day, 0)})
    return out


def weekly(series: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold a daily series into 7-day buckets, newest bucket ending today."""
    rows = list(series)
    start = len(rows) % 7
    out = []
    if start:
        out.append({"day": rows[0]["day"],
                    "total_tokens": sum(r["total_tokens"] for r in rows[:start])})
    for i in range(start, len(rows), 7):
        chunk = rows[i:i + 7]
        out.append({"day": chunk[0]["day"], "total_tokens": sum(r["total_tokens"] for r in chunk)})
    return out


def _every_other(labels: Sequence[str]) -> list[str]:
    """Keep one label in two, counted back from the latest. Qt needs distinct category
    names, so the blanks are runs of zero-width spaces of different lengths."""
    last = len(labels) - 1
    return [label if (last - i) % 2 == 0 else "\u200b" * (i + 1)
            for i, label in enumerate(labels)]


def _gb(n: float, binary: bool = True) -> str:
    """Memory in the units macOS shows (an 8 GB Mac reads '8,0 Go'); disks are
    sold and shown by Finder in decimal units."""
    return f"{n / (2**30 if binary else 1e9):.1f} Go".replace(".", ",")


def _mem(n: float) -> str:
    """'1,3 Go', or '45 Mo' under a gigabyte so small apps don't read '0,0 Go'."""
    return _gb(n) if n >= 2**30 * 0.95 else f"{n / 2**20:.0f} Mo"


def _money(amount: float) -> str:
    return f"{amount:,.0f} $".replace(",", " ")


def pretty_model(model: str) -> str:
    """'claude-opus-5-5' -> 'Opus 5.5', 'claude-haiku-4-5-20251001' -> 'Haiku 4.5'."""
    name = re.sub(r"-\d{8}$", "", str(model or "")).removeprefix("claude-")
    family, _, version = name.partition("-")
    if not family:
        return str(model or "")
    version = version.replace("-", ".")
    return f"{family.capitalize()} {version}".strip()


def updated_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 5:
        return "mis à jour à l'instant"
    if seconds < 60:
        return f"mis à jour il y a {seconds} s"
    return f"mis à jour il y a {seconds // 60} min"


def _delta(current: float, previous: float, against: str) -> tuple[str, str | None]:
    if not previous:
        return f"rien {against}", None
    pct = (current - previous) / previous * 100
    arrow = "▲" if pct >= 0 else "▼"
    tone = _UP if pct >= 0 else _DOWN
    if pct >= 200:  # "▲ 3051 %" reads worse than "× 31"
        return f"{arrow} × {current / previous:.0f} {against}", tone
    return f"{arrow} {abs(pct):.0f} % {against}", tone


def _long_day(day: str) -> str:
    try:
        date = dt.date.fromisoformat(day)
    except ValueError:
        return day
    return f"{date.day} {_MONTHS[date.month - 1]}"


def plain_label(text: str, limit: int = 14) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _comparison(cap, period: str) -> dict[str, Any] | None:
    """Tokens of the window just before the selected one, for the change
    shown on the Tokens card. None for "Tout", which has no "before"."""
    if period == "today":
        return {"previous": cap.overview("yesterday").data.get("total_tokens", 0),
                "against": "vs hier"}
    if period in ("7d", "30d"):
        data = cap.compare(period).data
        days = data.get("days")
        return {"previous": data.get("previous", {}).get("total_tokens", 0),
                "against": f"vs les {days} j d'avant"}
    return None
