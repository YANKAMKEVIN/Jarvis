"""QtCharts panels for Jarvis introspection (token usage and machine metrics).
Pure view code: it takes already-aggregated series (the dicts the capabilities
return) and renders them. No data access here, so it stays testable off a fixed
payload and reusable for any series. The windows at the bottom load the data on
a background thread and hand it to these builders.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from typing import Any, Sequence

from PySide6.QtCharts import (
    QAreaSeries, QBarCategoryAxis, QBarSet, QChart, QChartView, QDateTimeAxis,
    QHorizontalBarSeries, QLineSeries, QStackedBarSeries, QValueAxis,
)
from PySide6.QtCore import QDateTime, QMargins, QObject, QPointF, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGradient, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGraphicsSimpleTextItem, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QProgressBar, QPushButton, QToolTip, QVBoxLayout, QWidget,
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


def _show_tip(text: str) -> None:
    QToolTip.showText(QCursor.pos(), text)


def _style_chart(chart: QChart) -> None:
    """Bare chart: the panel around it carries the title, the plot uses the
    whole area."""
    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)
    chart.setBackgroundRoundness(0)
    chart.legend().setVisible(False)
    chart.setMargins(QMargins(2, 6, 8, 2))
    chart.layout().setContentsMargins(0, 0, 0, 0)
    chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)


def _small_font(size: int = 11) -> QFont:
    # Pixels, like the panel stylesheets ("font-size: 12px"), so chart text
    # stays in proportion with the labels around it.
    font = QFont()
    font.setPixelSize(size)
    return font


def _style_axes(*axes) -> None:
    for axis in axes:
        axis.setLabelsFont(_small_font(11))
        axis.setLabelsColor(QColor(_MUTED))
        axis.setGridLineColor(QColor(255, 255, 255, 16))
        axis.setLinePenColor(QColor(255, 255, 255, 36))
        axis.setTitleVisible(False)


def _value_axis(top: float) -> QValueAxis:
    axis = QValueAxis()
    axis.setRange(0, top or 1)
    axis.applyNiceNumbers()  # round ticks (0, 500, 1000…) instead of 0, 546, 1092…
    axis.setLabelFormat("%.1f" if axis.max() < 5 else "%.0f")
    return axis


def _view(chart: QChart) -> QChartView:
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setStyleSheet("background: transparent;")
    view.setMinimumHeight(170)
    return view


def _panel(title: str, body: QWidget, legend: str = "") -> QFrame:
    """Rounded panel with a left-aligned title (and an optional legend on the
    right) above a chart or a list."""
    panel = QFrame()
    panel.setObjectName("chartPanel")
    panel.setStyleSheet(f"#chartPanel {{ background: {_PANEL}; border-radius: 14px; }}")
    box = QVBoxLayout(panel)
    box.setContentsMargins(16, 12, 12, 10)
    box.setSpacing(4)
    head = QHBoxLayout()
    title_label = QLabel(title)
    title_label.setObjectName("panelTitle")
    title_label.setStyleSheet(f"color: {_TEXT}; font-size: 14px; font-weight: 600;")
    head.addWidget(title_label)
    head.addStretch(1)
    if legend:
        legend_label = QLabel(legend)
        legend_label.setObjectName("panelLegend")
        legend_label.setTextFormat(Qt.TextFormat.RichText)
        legend_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        head.addWidget(legend_label)
    box.addLayout(head)
    box.addWidget(body, 1)
    return panel


def _swatch(color: str, text: str) -> str:
    return f"<span style='color:{color}; font-size:15px'>●</span> {text}"


def _daily_chart(labels: Sequence[str], values: Sequence[float], tips: Sequence[str],
                 today: int | None, peak: int | None) -> QChartView:
    """Vertical token bars in an automatic unit. Today and the peak get their
    own colour through a stacked series (Qt colours per set, not per bar)."""
    divisor, _ = _unit(values)
    scaled = [v / divisor for v in values]
    layers = (
        (_ACCENTS[0], [v if i not in (today, peak) else 0 for i, v in enumerate(scaled)]),
        (_PEAK, [v if i == peak and i != today else 0 for i, v in enumerate(scaled)]),
        (_TODAY, [v if i == today else 0 for i, v in enumerate(scaled)]),
    )
    series = QStackedBarSeries()
    series.setBarWidth(0.78)
    for color, layer in layers:
        bar_set = QBarSet("")
        bar_set.append(layer)
        bar_set.setColor(QColor(color))
        bar_set.setBorderColor(QColor(color))
        bar_set.hovered.connect(
            lambda on, index: _show_tip(tips[index]) if on else QToolTip.hideText())
        series.append(bar_set)

    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart)
    cat_axis = QBarCategoryAxis()
    cat_axis.append(list(labels))
    cat_axis.setTruncateLabels(False)  # Qt elides short labels like "16" to "…" otherwise
    cat_axis.setGridLineVisible(False)
    val_axis = _value_axis(max(scaled, default=0) * 1.1)
    chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(val_axis, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(cat_axis)
    series.attachAxis(val_axis)
    _style_axes(cat_axis, val_axis)
    return _view(chart)


def _ranking_chart(names: Sequence[str], values: Sequence[float], color: str,
                   tips: Sequence[str]) -> QChartView:
    """Horizontal bars, largest on top, each with its value written at its
    end; no value axis, the numbers say it."""
    names, values, tips = list(names)[::-1], list(values)[::-1], list(tips)[::-1]
    divisor, _ = _unit(values)
    scaled = [v / divisor for v in values]
    bar_set = QBarSet("")
    bar_set.append(scaled)
    bar_set.setColor(QColor(color))
    bar_set.setBorderColor(QColor(color))
    bar_set.hovered.connect(
        lambda on, index: _show_tip(tips[index]) if on else QToolTip.hideText())
    series = QHorizontalBarSeries()
    series.append(bar_set)
    series.setBarWidth(0.62)

    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart)
    chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)  # labels sit at the final length
    cat_axis = QBarCategoryAxis()
    cat_axis.append(names)
    cat_axis.setTruncateLabels(False)
    cat_axis.setGridLineVisible(False)
    cat_axis.setLineVisible(False)
    val_axis = QValueAxis()
    val_axis.setRange(0, (max(scaled, default=0) or 1) * 1.3)  # room for the end labels
    val_axis.setVisible(False)
    chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignLeft)
    chart.addAxis(val_axis, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(cat_axis)
    series.attachAxis(val_axis)
    _style_axes(cat_axis)
    cat_axis.setLabelsColor(QColor(_TEXT))
    cat_axis.setLabelsFont(_small_font(13))

    texts = [_human(v) for v in values]
    items = []
    for text in texts:
        item = QGraphicsSimpleTextItem(text, chart)
        item.setBrush(QColor(_MUTED))
        item.setFont(_small_font(12))
        items.append(item)

    def place() -> None:
        for index, (value, item) in enumerate(zip(scaled, items)):
            point = chart.mapToPosition(QPointF(value, index), series)
            item.setPos(point.x() + 6, point.y() - item.boundingRect().height() / 2)

    chart.plotAreaChanged.connect(lambda _area: place())
    place()
    return _view(chart)


def _line_chart(series: Sequence[dict[str, Any]], color: str, period: str = "24h",
                threshold: float | None = None) -> QChartView:
    """Percentage over time as a filled curve, with real clock labels and,
    when given, the alert threshold as a dashed line."""
    upper = QLineSeries()
    points = [(float(p["ts"]) * 1000, float(p["value"])) for p in series]
    for x, y in points:
        upper.append(x, y)
    area = QAreaSeries(upper)
    upper.setParent(area)  # the area does not own its boundary series
    pen = QPen(QColor(color))
    pen.setWidth(2)
    area.setPen(pen)
    gradient = QLinearGradient(0, 0, 0, 1)
    gradient.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
    top, bottom = QColor(color), QColor(color)
    top.setAlpha(110)
    bottom.setAlpha(0)
    gradient.setColorAt(0, top)
    gradient.setColorAt(1, bottom)
    area.setBrush(gradient)
    clock = "dd/MM HH:mm" if period == "7d" else "HH:mm"

    def hover(point: QPointF, on: bool) -> None:
        if not on:
            QToolTip.hideText()
            return
        x, y = min(points, key=lambda p: abs(p[0] - point.x()))
        when = QDateTime.fromMSecsSinceEpoch(int(x)).toString(clock)
        _show_tip(f"{when} · {y:.0f} %")

    area.hovered.connect(hover)

    chart = QChart()
    chart.addSeries(area)
    _style_chart(chart)

    first, last = points[0][0], points[-1][0]
    if last <= first:
        last = first + 60_000
    axis_x = QDateTimeAxis()
    axis_x.setFormat("dd/MM" if period == "7d" else "HH:mm")
    axis_x.setTickCount(6)
    axis_x.setRange(QDateTime.fromMSecsSinceEpoch(int(first)),
                    QDateTime.fromMSecsSinceEpoch(int(last)))
    axis_x.setGridLineVisible(False)
    axis_y = QValueAxis()
    axis_y.setRange(0, 100)
    axis_y.setTickCount(5)
    axis_y.setLabelFormat("%.0f")
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    area.attachAxis(axis_x)
    area.attachAxis(axis_y)

    if threshold is not None:
        limit = QLineSeries()
        limit.append(first, threshold)
        limit.append(last, threshold)
        dash = QPen(QColor(_ALERT))
        dash.setWidth(1)
        dash.setStyle(Qt.PenStyle.DashLine)
        chart.addSeries(limit)
        limit.setPen(dash)  # after addSeries, or the chart theme repaints it
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
    box.addStretch(1)
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


def _apps_list(apps: Sequence[dict[str, Any]]) -> QWidget:
    """One gauge per app, its length relative to the heaviest app."""
    body = QWidget()
    grid = QGridLayout(body)
    grid.setContentsMargins(0, 4, 4, 2)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(8)
    grid.setColumnStretch(1, 1)
    rows = list(apps[:6])
    weight = lambda r: r.get("bytes") or r.get("value") or 0
    top = max((weight(r) for r in rows), default=0) or 1
    for i, row in enumerate(rows):
        name = QLabel(plain_label(row.get("name"), 26))
        name.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
        gauge = QProgressBar()
        gauge.setObjectName("appGauge")
        gauge.setRange(0, 1000)
        gauge.setValue(int(weight(row) / top * 1000))
        gauge.setTextVisible(False)
        gauge.setFixedHeight(8)
        gauge.setStyleSheet(
            "#appGauge { background: #1b2a3d; border: none; border-radius: 4px; }"
            f"#appGauge::chunk {{ background: {_ACCENTS[i % 3]}; border-radius: 4px; }}")
        if row.get("bytes"):
            count = row.get("processes", 0)
            amount = _mem(row["bytes"]) + (f" · {count} processus" if count > 1 else "")
        else:  # plain per-process rows (value = % of memory)
            amount = f"{row.get('value')} %"
        value = QLabel(amount)
        value.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(name, i, 0)
        grid.addWidget(gauge, i, 1)
        grid.addWidget(value, i, 2)
    return body


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
    *,
    updated_at: float | None = None,
) -> QWidget:
    """Machine-activity dashboard: live figures, CPU/memory history against the
    alert thresholds, and the apps holding the most memory. With `updated_at`,
    a "mis à jour il y a…" label (object name "updated") sits by the periods."""
    root, layout = _dashboard_root("metricsDashboard", "Activité machine")
    if parent is not None:
        root.setParent(parent)

    if on_period_change is not None:
        trailing = None
        if updated_at is not None:
            trailing = QLabel(updated_text(time.time() - updated_at))
            trailing.setObjectName("updated")
            trailing.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        layout.addWidget(_period_bar(period, on_period_change, METRIC_PERIODS, trailing))

    if snapshot:
        layout.addWidget(_metrics_cards(snapshot))

    limits = Thresholds()
    label = {"1h": "1 h", "6h": "6 h", "24h": "24 h", "7d": "7 j"}.get(period, "24 h")
    dashed = _swatch(_ALERT, "seuil d'alerte")
    if cpu_series:
        layout.addWidget(_panel(f"Processeur · % sur {label}",
                                _line_chart(cpu_series, _ACCENTS[0], period, limits.cpu_percent),
                                dashed), 1)
    if mem_series:
        layout.addWidget(_panel(f"Mémoire · % sur {label}",
                                _line_chart(mem_series, _ACCENTS[1], period, limits.mem_percent),
                                dashed), 1)
    if not cpu_series and not mem_series:
        note = QLabel("L'historique se remplit pendant que Jarvis tourne. "
                      "Reviens dans quelques minutes pour voir les courbes.")
        note.setObjectName("sub")
        note.setWordWrap(True)
        layout.addWidget(note)

    if processes:
        layout.addWidget(_panel("Applications les plus gourmandes en mémoire",
                                _apps_list(processes)))

    if not cpu_series and not mem_series and not processes:
        layout.addStretch(1)

    return root


def _period_bar(current: str, on_change, periods: Sequence = USAGE_PERIODS,
                trailing: QWidget | None = None) -> QWidget:
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
    if trailing is not None:
        row.addWidget(trailing)
    return bar


def _long_day(day: str) -> str:
    try:
        date = dt.date.fromisoformat(day)
    except ValueError:
        return day
    return f"{date.day} {_MONTHS[date.month - 1]}"


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
            buckets, title, now_word = weekly(daily), "Tokens par semaine", "cette semaine"
            labels = [_short_day(d["day"]) for d in buckets]
            labels = _every_other(labels) if len(labels) > 10 else labels
            tips = [f"Semaine du {_long_day(d['day'])} · {_human(d['total_tokens'])} tokens"
                    for d in buckets]
        else:
            buckets, title, now_word = daily, "Tokens par jour", "aujourd'hui"
            if len(daily) > 14:
                # A month of "16/10" does not fit under the bars: day numbers
                # only, one in two, and the months in the title.
                labels = _every_other([d["day"][-2:] for d in buckets])
                title += f" du {_short_day(daily[0]['day'])} au {_short_day(daily[-1]['day'])}"
            else:
                labels = [_short_day(d["day"]) for d in buckets]
            tips = [f"{_long_day(d['day'])} · {_human(d['total_tokens'])} tokens" for d in buckets]
        vals = [d["total_tokens"] for d in buckets]
        _, suffix = _unit(vals)
        if suffix:
            title += f" · {suffix}"
        current = len(buckets) - 1
        peak = max(range(len(vals)), key=vals.__getitem__) if any(vals) else None
        legend = [_swatch(_TODAY, now_word)]
        if peak is not None and peak != current:
            when = _short_day(buckets[peak]["day"])
            legend.append(_swatch(_PEAK, f"pic {when} · {_human(vals[peak])}"))
        elif peak == current:
            legend[0] = _swatch(_TODAY, f"{now_word}, le pic")
        layout.addWidget(_panel(title, _daily_chart(labels, vals, tips, current, peak),
                                "&nbsp;&nbsp;&nbsp;".join(legend)), 3)

    breakdown = QHBoxLayout()
    breakdown.setSpacing(12)
    if model_rows:
        rows = model_rows[:6]
        names = [pretty_model(r["model"]) for r in rows]
        tips = [f"{n} · {_human(r['total_tokens'])} tokens" for n, r in zip(names, rows)]
        breakdown.addWidget(_panel("Par modèle", _ranking_chart(
            names, [r["total_tokens"] for r in rows], _ACCENTS[1], tips)), 1)
    if project_rows:
        names = [plain_label(r["project"], 22) for r in project_rows]
        tips = [f"{r['project']} · {_human(r['total_tokens'])} tokens" for r in project_rows]
        breakdown.addWidget(_panel("Par projet", _ranking_chart(
            names, [r["total_tokens"] for r in project_rows], _ACCENTS[2], tips)), 1)
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
        # Keeps the "mis à jour il y a…" label honest between two refreshes.
        self._loaded_at: float | None = None
        self._ticker = QTimer(self)
        self._ticker.setInterval(5_000)
        self._ticker.timeout.connect(self._tick)
        self.reload()

    def showEvent(self, event) -> None:
        self._timer.start()
        self._ticker.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        self._ticker.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        label = self.findChild(QLabel, "updated")
        if label is not None and self._loaded_at is not None:
            label.setText(updated_text(time.time() - self._loaded_at))

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
        self._loaded_at = time.time()
        self.setCentralWidget(make_metrics_dashboard(
            snapshot, cpu, mem, apps, period, self._on_period, self,
            updated_at=self._loaded_at))

    def _show_error(self, message: str) -> None:
        label = QLabel(f"Activité machine indisponible.\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {_MUTED}; font-size: 14px;")
        self.setCentralWidget(label)
