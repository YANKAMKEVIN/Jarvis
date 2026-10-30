"""QtCharts panels for Jarvis introspection (token usage and machine metrics).
Pure view code: it takes already-aggregated series (the dicts the capabilities
return) and renders them. No data access here, so it stays testable off a fixed
payload and reusable for any series. The windows at the bottom load the data on
a background thread and hand it to these builders.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QDateTimeAxis,
    QHorizontalBarSeries, QLineSeries, QValueAxis,
)
from PySide6.QtCore import QDateTime, QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget,
)

from jarvis.capabilities.usage import _human
from jarvis.insights.detector import Thresholds

# Shared palette, aligned with the desktop dark theme.
_BG = "#0b111b"
_PANEL = "#121d2b"
_TEXT = "#dce8f6"
_MUTED = "#93a7bc"
_UP = "#f6c177"     # more tokens than before: worth a look, not an error
_DOWN = "#8af0e0"
_ALERT = "#f0a7ba"
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


def _money(amount: float) -> str:
    return f"{amount:,.0f} $".replace(",", " ")


def _style_chart(chart: QChart, title: str) -> None:
    chart.setTitle(title)
    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)
    chart.legend().setVisible(False)
    chart.setTitleBrush(QColor(_TEXT))
    title_font = QFont()
    title_font.setPointSize(13)
    title_font.setBold(True)
    chart.setTitleFont(title_font)
    chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)


def _style_axes(*axes) -> None:
    for axis in axes:
        axis.setLabelsColor(QColor(_MUTED))
        axis.setGridLineColor(QColor(255, 255, 255, 18))
        axis.setLinePenColor(QColor(255, 255, 255, 40))


def _value_axis(top: float, title: str) -> QValueAxis:
    axis = QValueAxis()
    axis.setRange(0, top or 1)
    axis.applyNiceNumbers()  # round ticks (0, 500, 1000…) instead of 0, 546, 1092…
    axis.setLabelFormat("%.1f" if axis.max() < 5 else "%.0f")
    axis.setTitleText(title)
    axis.setTitleBrush(QColor(_MUTED))
    return axis


def _view(chart: QChart) -> QChartView:
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setStyleSheet(f"background: {_PANEL}; border-radius: 14px;")
    return view


def _bar_chart(title: str, categories: Sequence[str], values: Sequence[float],
               color: str, horizontal: bool = False) -> QChartView:
    """Token bars in an automatic unit (k, M or Md). Horizontal bars list the
    largest first and keep long names readable."""
    divisor, suffix = _unit(values)
    scaled = [v / divisor for v in values]
    cats = list(categories)
    if horizontal:  # Qt draws the first category at the bottom
        cats, scaled = cats[::-1], scaled[::-1]

    bar_set = QBarSet("")
    bar_set.append(scaled)
    bar_set.setColor(QColor(color))
    bar_set.setBorderColor(QColor(color))
    series = QHorizontalBarSeries() if horizontal else QBarSeries()
    series.append(bar_set)
    series.setBarWidth(0.7 if horizontal else 0.85)

    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart, title)

    cat_axis = QBarCategoryAxis()
    cat_axis.append(cats)
    cat_axis.setTruncateLabels(False)  # Qt elides short labels like "16" to "…" otherwise
    val_axis = _value_axis(max(scaled, default=0) * 1.1, f"{suffix} tokens".strip())
    if horizontal:
        chart.addAxis(val_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignLeft)
    else:
        chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(val_axis, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(cat_axis)
    series.attachAxis(val_axis)
    _style_axes(cat_axis, val_axis)
    return _view(chart)


def _line_chart(title: str, series: Sequence[dict[str, Any]], color: str,
                y_title: str, period: str = "24h",
                threshold: float | None = None) -> QChartView:
    """Percentage over time with real clock labels and, when given, the alert
    threshold as a dashed line."""
    line = QLineSeries()
    for point in series:
        line.append(float(point["ts"]) * 1000, float(point["value"]))
    pen = line.pen()
    pen.setColor(QColor(color))
    pen.setWidth(2)
    line.setPen(pen)

    chart = QChart()
    chart.addSeries(line)
    _style_chart(chart, title)

    first = float(series[0]["ts"]) * 1000
    last = float(series[-1]["ts"]) * 1000
    if last <= first:
        last = first + 60_000
    axis_x = QDateTimeAxis()
    axis_x.setFormat("dd/MM" if period == "7d" else "HH:mm")
    axis_x.setTickCount(6)
    axis_x.setRange(QDateTime.fromMSecsSinceEpoch(int(first)),
                    QDateTime.fromMSecsSinceEpoch(int(last)))
    axis_y = QValueAxis()
    axis_y.setRange(0, 100)
    axis_y.setTickCount(5)
    axis_y.setLabelFormat("%.0f")
    axis_y.setTitleText(y_title)
    axis_y.setTitleBrush(QColor(_MUTED))
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    line.attachAxis(axis_x)
    line.attachAxis(axis_y)

    if threshold is not None:
        limit = QLineSeries()
        limit.setName("seuil")
        limit.append(first, threshold)
        limit.append(last, threshold)
        dash = QPen(QColor(_ALERT))
        dash.setWidth(1)
        dash.setStyle(Qt.PenStyle.DashLine)
        limit.setPen(dash)
        chart.addSeries(limit)
        limit.attachAxis(axis_x)
        limit.attachAxis(axis_y)

    _style_axes(axis_x, axis_y)
    return _view(chart)


def _stat_card(title: str, value: str, detail: str = "", tone: str | None = None) -> QFrame:
    card = QFrame()
    card.setObjectName("statCard")
    card.setStyleSheet(f"#statCard {{ background: {_PANEL}; border-radius: 14px; }}")
    box = QVBoxLayout(card)
    box.setContentsMargins(16, 12, 16, 12)
    box.setSpacing(2)
    head = QLabel(title)
    head.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
    big = QLabel(value)
    big.setObjectName("statValue")
    big.setStyleSheet(f"color: {_TEXT}; font-size: 22px; font-weight: 600;")
    box.addWidget(head)
    box.addWidget(big)
    if detail:
        small = QLabel(detail)
        small.setWordWrap(True)
        small.setStyleSheet(f"color: {tone or _MUTED}; font-size: 12px;")
        box.addWidget(small)
    return card


def _cards_row(cards: Sequence[QFrame]) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for card in cards:
        layout.addWidget(card, 1)
    return row


def _delta(current: float, previous: float, against: str) -> tuple[str, str | None]:
    if not previous:
        return f"rien {against}", None
    pct = (current - previous) / previous * 100
    arrow = "▲" if pct >= 0 else "▼"
    tone = _UP if pct >= 0 else _DOWN
    if pct >= 200:  # "▲ 3051 %" reads worse than "× 31"
        return f"{arrow} × {current / previous:.0f} {against}", tone
    return f"{arrow} {abs(pct):.0f} % {against}", tone


def _usage_cards(overview: dict[str, Any], cost: float,
                 comparison: dict[str, Any] | None) -> QWidget:
    total = overview.get("total_tokens", 0)
    detail, tone = "", None
    if comparison:
        detail, tone = _delta(total, comparison.get("previous", 0), comparison.get("against", ""))
    cache = overview.get("cache_read", 0)
    cards = [
        _stat_card("Tokens", _human(total), detail, tone),
        _stat_card("Générés", _human(overview.get("output", 0)),
                   f"{_human(cache)} relus en cache" if cache else ""),
        _stat_card("Sessions", str(overview.get("sessions", 0)),
                   f"sur {overview['days']} jours actifs" if overview.get("days", 0) > 1 else ""),
    ]
    if cost:
        cards.append(_stat_card("Coût équivalent API", _money(cost),
                                "indicatif : l'abonnement n'est pas facturé au token"))
    return _cards_row(cards)


def _metrics_cards(snapshot: dict[str, Any]) -> QWidget:
    limits = Thresholds()

    def tone(value: float, limit: float) -> str | None:
        return _ALERT if value >= limit else None

    cpu = snapshot.get("cpu", 0)
    mem = snapshot.get("mem", 0)
    disk = snapshot.get("disk", 0)
    mem_detail = ""
    if snapshot.get("mem_total"):
        # psutil's "used" leaves out compressed and wired pages on macOS, so it
        # disagrees with the percentage; derive the figure from the percentage.
        total = snapshot["mem_total"]
        mem_detail = f"{_gb(total * mem / 100)} sur {_gb(total)}"
    disk_detail = ""
    if snapshot.get("disk_total"):
        free = snapshot["disk_total"] - snapshot.get("disk_used", 0)
        disk_detail = f"{_gb(free, binary=False)} libres"
    cards = [
        _stat_card("Processeur", f"{cpu:.0f} %",
                   "au-dessus du seuil d'alerte" if tone(cpu, limits.cpu_percent) else "",
                   tone(cpu, limits.cpu_percent)),
        _stat_card("Mémoire", f"{mem:.0f} %", mem_detail, tone(mem, limits.mem_percent)),
        _stat_card("Disque", f"{disk:.0f} %", disk_detail, tone(disk, limits.disk_percent)),
    ]
    if snapshot.get("battery") is not None:
        plugged = snapshot.get("power_plugged")
        cards.append(_stat_card("Batterie", f"{snapshot['battery']:.0f} %",
                                "branchée" if plugged else "sur batterie"))
    return _cards_row(cards)


def _apps_panel(apps: Sequence[dict[str, Any]]) -> QWidget:
    panel = QWidget()
    panel.setObjectName("appsPanel")
    panel.setStyleSheet(f"#appsPanel {{ background: {_PANEL}; border-radius: 14px; }}")
    box = QVBoxLayout(panel)
    box.setContentsMargins(16, 14, 16, 14)
    box.setSpacing(6)
    title = QLabel("Applications les plus gourmandes (mémoire)")
    title.setStyleSheet(f"color: {_TEXT}; font-size: 14px; font-weight: 600;")
    box.addWidget(title)
    for row in apps[:6]:
        name = plain_label(row.get("name"), 32)
        if row.get("bytes"):
            count = row.get("processes", 0)
            extra = f"  ·  {count} processus" if count > 1 else ""
            text = f"{name}  ·  {_gb(row['bytes'])}{extra}"
        else:  # plain per-process rows (value = % of memory)
            text = f"{name}  ·  {row.get('value')} %"
        line = QLabel(text)
        line.setStyleSheet(f"color: {_MUTED}; font-size: 13px;")
        box.addWidget(line)
    return panel


def _dashboard_root(name: str, heading: str) -> tuple[QWidget, QVBoxLayout]:
    root = QWidget()
    root.setObjectName(name)
    root.setStyleSheet(
        f"#{name} {{ background: {_BG}; }}"
        f"QLabel {{ color: {_TEXT}; }}"
        f"QLabel#sub {{ color: {_MUTED}; font-size: 13px; }}"
    )
    layout = QVBoxLayout(root)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    title = QLabel(heading)
    title.setStyleSheet("font-size: 19px; font-weight: 600;")
    layout.addWidget(title)
    return root, layout


def make_metrics_dashboard(
    snapshot: dict[str, Any],
    cpu_series: Sequence[dict[str, Any]],
    mem_series: Sequence[dict[str, Any]],
    processes: Sequence[dict[str, Any]] = (),
    period: str = "",
    on_period_change=None,
    parent: QWidget | None = None,
) -> QWidget:
    """Machine-activity dashboard: live figures, CPU/memory history against the
    alert thresholds, and the apps holding the most memory."""
    root, layout = _dashboard_root("metricsDashboard", "Activité machine")
    if parent is not None:
        root.setParent(parent)

    if on_period_change is not None:
        layout.addWidget(_period_bar(period, on_period_change, METRIC_PERIODS))

    if snapshot:
        layout.addWidget(_metrics_cards(snapshot))

    limits = Thresholds()
    label = {"1h": "1 h", "6h": "6 h", "24h": "24 h", "7d": "7 j"}.get(period, "24 h")
    if cpu_series:
        layout.addWidget(_line_chart(f"Processeur ({label})", cpu_series, _ACCENTS[0],
                                     "% CPU", period, limits.cpu_percent), 1)
    if mem_series:
        layout.addWidget(_line_chart(f"Mémoire ({label})", mem_series, _ACCENTS[1],
                                     "% mémoire", period, limits.mem_percent), 1)
    if not cpu_series and not mem_series:
        note = QLabel("L'historique se remplit pendant que Jarvis tourne. "
                      "Reviens dans quelques minutes pour voir les courbes.")
        note.setObjectName("sub")
        note.setWordWrap(True)
        layout.addWidget(note)
    else:
        legend = QLabel("Pointillés : seuil d'alerte "
                        f"({limits.cpu_percent:.0f} % processeur, "
                        f"{limits.mem_percent:.0f} % mémoire, en moyenne sur 5 min).")
        legend.setObjectName("sub")
        layout.addWidget(legend)

    if processes:
        layout.addWidget(_apps_panel(processes))

    if not cpu_series and not mem_series and not processes:
        layout.addStretch(1)

    return root


def _period_bar(current: str, on_change, periods: Sequence = USAGE_PERIODS) -> QWidget:
    bar = QWidget()
    row = QHBoxLayout(bar)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    for key, label in periods:
        active = key == current
        button = QPushButton(label)
        button.setCheckable(True)
        button.setChecked(active)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            "QPushButton { padding: 5px 14px; border-radius: 13px; border: none; "
            f"color: {'#081421' if active else _TEXT}; "
            f"background: {_ACCENTS[0] if active else _PANEL}; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {_ACCENTS[0] if active else '#1b2a3d'}; }}"
        )
        button.clicked.connect(lambda _checked=False, k=key: on_change(k))
        row.addWidget(button)
    row.addStretch(1)
    return bar


def make_usage_dashboard(
    overview: dict[str, Any],
    trend_series: Sequence[dict[str, Any]],
    model_rows: Sequence[dict[str, Any]],
    project_rows: Sequence[dict[str, Any]] = (),
    period: str = "",
    on_period_change=None,
    parent: QWidget | None = None,
    *,
    comparison: dict[str, Any] | None = None,
    today: dt.date | None = None,
) -> QWidget:
    """Build the token-usage dashboard widget from aggregated payloads.

    `trend_series` is the store's daily rows; the chart fills idle days with
    zero over the period's span and switches to weeks past a month.
    `comparison` ({"previous": tokens, "against": "vs hier"}) adds the change
    to the Tokens card.
    """
    root, layout = _dashboard_root("usageDashboard", "Consommation de tokens")
    if parent is not None:
        root.setParent(parent)

    if on_period_change is not None:
        layout.addWidget(_period_bar(period, on_period_change))

    cost = sum(r.get("est_cost_usd", 0) or 0 for r in model_rows)
    if overview:
        if overview.get("period"):
            sub = QLabel(overview["period"].capitalize())
            sub.setObjectName("sub")
            layout.addWidget(sub)
        layout.addWidget(_usage_cards(overview, cost, comparison))

    if trend_series:
        days = TREND_DAYS.get(period) or max(2, len(trend_series))
        daily = fill_days(trend_series, days, today)
        if len(daily) > _WEEKLY_AFTER:
            buckets, title = weekly(daily), "Tokens par semaine"
            labels = [_short_day(d["day"]) for d in buckets]
            cats = _every_other(labels) if len(labels) > 10 else labels
        else:
            buckets, title = daily, "Tokens par jour"
            if len(daily) > 14:
                # A month of "16/10" does not fit under the bars: day numbers
                # only, one in two, and the months in the title.
                cats = _every_other([d["day"][-2:] for d in buckets])
                title += f" ({_short_day(daily[0]['day'])} → {_short_day(daily[-1]['day'])})"
            else:
                cats = [_short_day(d["day"]) for d in buckets]
            if period == "today":
                title += " (7 derniers jours)"
        vals = [d["total_tokens"] for d in buckets]
        layout.addWidget(_bar_chart(title, cats, vals, _ACCENTS[0]), 3)

    breakdown = QHBoxLayout()
    breakdown.setSpacing(12)
    if model_rows:
        cats = [r["model"].replace("claude-", "") for r in model_rows[:6]]
        vals = [r["total_tokens"] for r in model_rows[:6]]
        breakdown.addWidget(_bar_chart("Par modèle", cats, vals, _ACCENTS[1], horizontal=True), 1)
    if project_rows:
        cats = [plain_label(r["project"], 22) for r in project_rows]
        vals = [r["total_tokens"] for r in project_rows]
        breakdown.addWidget(_bar_chart("Par projet", cats, vals, _ACCENTS[2], horizontal=True), 1)
    if breakdown.count():
        layout.addLayout(breakdown, 3)

    return root


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


class _UsageLoader(QObject):
    """Pulls the aggregates off the UI thread (a cold index pass takes a few
    seconds, which must never freeze the window)."""

    done = Signal(dict, list, list, list, str, object)
    failed = Signal(str)

    def __init__(self, period: str = "30d"):
        super().__init__()
        self.period = period

    def run(self) -> None:
        try:
            from jarvis.capabilities.usage import UsageCapability

            cap = UsageCapability()
            overview = cap.overview(self.period).data
            trend = cap.trend(TREND_DAYS.get(self.period, 30)).data.get("series", [])
            models = cap.by_model(self.period).data.get("models", [])
            projects = cap.by_project(self.period, 6).data.get("projects", [])
            comparison = _comparison(cap, self.period)
        except Exception as error:  # pragma: no cover - defensive
            self.failed.emit(str(error))
            return
        self.done.emit(overview, trend, models, projects, self.period, comparison)


class UsageWindow(QMainWindow):
    """Standalone token-usage dashboard window, loaded asynchronously."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Jarvis · Consommation de tokens")
        self.resize(900, 820)
        self.setStyleSheet(f"QMainWindow {{ background: {_BG}; }}")
        self._thread: QThread | None = None
        self._loader: _UsageLoader | None = None
        self._period = "30d"
        self.reload()

    def reload(self, period: str | None = None) -> None:
        if period:
            self._period = period
        if self._thread is not None and self._thread.isRunning():
            return
        placeholder = QLabel("Chargement du graphe…")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet(f"color: {_MUTED}; font-size: 15px;")
        self.setCentralWidget(placeholder)

        self._thread = QThread(self)
        self._loader = _UsageLoader(self._period)
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.done.connect(self._populate)
        self._loader.failed.connect(self._show_error)
        self._loader.done.connect(self._thread.quit)
        self._loader.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_period(self, key: str) -> None:
        self.reload(key)

    def _populate(self, overview: dict, trend: list, models: list,
                  projects: list, period: str, comparison) -> None:
        self.setCentralWidget(make_usage_dashboard(
            overview, trend, models, projects, period, self._on_period, self,
            comparison=comparison))

    def _show_error(self, message: str) -> None:
        label = QLabel(f"Lecture de l'usage impossible.\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {_MUTED}; font-size: 14px;")
        self.setCentralWidget(label)


class _MetricsLoader(QObject):
    done = Signal(dict, list, list, list, str)
    failed = Signal(str)

    def __init__(self, period: str = "24h"):
        super().__init__()
        self.period = period

    def run(self) -> None:
        try:
            from jarvis.capabilities.system_metrics import SystemMetricsCapability

            cap = SystemMetricsCapability()
            snapshot = cap.snapshot().data
            cpu = cap.history("cpu", self.period).data.get("series", [])
            mem = cap.history("mem", self.period).data.get("series", [])
            apps = cap.top_apps(6).data.get("apps", [])
        except Exception as error:  # pragma: no cover - defensive
            self.failed.emit(str(error))
            return
        self.done.emit(snapshot, cpu, mem, apps, self.period)


class MetricsWindow(QMainWindow):
    """Standalone machine-activity dashboard window, loaded asynchronously and
    refreshed every 30 s while it is on screen."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Jarvis · Activité machine")
        self.resize(900, 860)
        self.setStyleSheet(f"QMainWindow {{ background: {_BG}; }}")
        self._thread: QThread | None = None
        self._loader: _MetricsLoader | None = None
        self._period = "24h"
        self._timer = QTimer(self)
        self._timer.setInterval(METRICS_REFRESH_MS)
        self._timer.timeout.connect(lambda: self.reload(quiet=True))
        self.reload()

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def reload(self, period: str | None = None, quiet: bool = False) -> None:
        """Re-read the data. A quiet reload (the timer) keeps the current
        charts on screen until the new ones are ready, so nothing flickers."""
        if period:
            self._period = period
        if self._thread is not None and self._thread.isRunning():
            return
        if not quiet:
            placeholder = QLabel("Lecture de l'activité machine…")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet(f"color: {_MUTED}; font-size: 15px;")
            self.setCentralWidget(placeholder)

        self._thread = QThread(self)
        self._loader = _MetricsLoader(self._period)
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.done.connect(self._populate)
        self._loader.failed.connect(self._show_error)
        self._loader.done.connect(self._thread.quit)
        self._loader.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_period(self, key: str) -> None:
        self.reload(key)

    def _populate(self, snapshot: dict, cpu: list, mem: list,
                  apps: list, period: str) -> None:
        self.setCentralWidget(make_metrics_dashboard(
            snapshot, cpu, mem, apps, period, self._on_period, self))

    def _show_error(self, message: str) -> None:
        label = QLabel(f"Activité machine indisponible.\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {_MUTED}; font-size: 14px;")
        self.setCentralWidget(label)
