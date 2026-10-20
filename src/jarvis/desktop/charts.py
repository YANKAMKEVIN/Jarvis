"""QtCharts panels for Jarvis introspection (token usage, and later machine
metrics). Pure view code: it takes already-aggregated series (the dicts the
usage capability returns) and renders them. No data access here, so it stays
testable off a fixed payload and reusable for any series.
"""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget,
)

from jarvis.capabilities.usage import _human

# Shared palette, aligned with the desktop dark theme.
_BG = "#0b111b"
_PANEL = "#121d2b"
_TEXT = "#dce8f6"
_MUTED = "#93a7bc"
_ACCENTS = ["#82caff", "#8af0e0", "#bea5ff", "#f0a7ba", "#9ad0ea", "#f6c177"]


def _short_day(day: str) -> str:
    # '2026-10-16' -> '16/10'
    try:
        _, m, d = day.split("-")
        return f"{d}/{m}"
    except ValueError:
        return day


def _millions(n: float) -> float:
    return round(n / 1_000_000, 2)


def _style_chart(chart: QChart, title: str) -> None:
    chart.setTitle(title)
    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)
    chart.setMargins(chart.margins())
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
        if isinstance(axis, QValueAxis):
            axis.setLabelFormat("%.0f")


def _bar_chart(title: str, categories: Sequence[str], values: Sequence[float],
               colors: Sequence[str], y_title: str) -> QChartView:
    bar_set = QBarSet("")
    bar_set.append(list(values))
    # Per-bar colour via a single set is not supported; use one set but colour
    # it with the first accent, which reads cleanly on the dark panel.
    bar_set.setColor(QColor(colors[0]))
    bar_set.setBorderColor(QColor(colors[0]))

    series = QBarSeries()
    series.append(bar_set)
    series.setBarWidth(0.85)

    chart = QChart()
    chart.addSeries(series)
    _style_chart(chart, title)

    axis_x = QBarCategoryAxis()
    axis_x.append(list(categories))
    axis_y = QValueAxis()
    axis_y.setTitleText(y_title)
    axis_y.setTitleBrush(QColor(_MUTED))
    top = max(values) if values else 1
    axis_y.setRange(0, top * 1.15 or 1)
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(axis_x)
    series.attachAxis(axis_y)
    _style_axes(axis_x, axis_y)

    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setStyleSheet(f"background: {_PANEL}; border-radius: 14px;")
    return view


def _line_chart(title: str, series: Sequence[dict[str, Any]], color: str,
                y_title: str, y_max: float = 100.0) -> QChartView:
    line = QLineSeries()
    for i, point in enumerate(series):
        line.append(float(i), float(point["value"]))
    pen = line.pen()
    pen.setColor(QColor(color))
    pen.setWidth(2)
    line.setPen(pen)

    chart = QChart()
    chart.addSeries(line)
    _style_chart(chart, title)

    axis_x = QValueAxis()
    axis_x.setRange(0, max(1, len(series) - 1))
    axis_x.setLabelsVisible(False)
    axis_y = QValueAxis()
    axis_y.setRange(0, y_max)
    axis_y.setTitleText(y_title)
    axis_y.setTitleBrush(QColor(_MUTED))
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    line.attachAxis(axis_x)
    line.attachAxis(axis_y)
    _style_axes(axis_x, axis_y)

    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setStyleSheet(f"background: {_PANEL}; border-radius: 14px;")
    return view


def _process_panel(processes: Sequence[dict[str, Any]]) -> QWidget:
    panel = QWidget()
    panel.setStyleSheet(f"background: {_PANEL}; border-radius: 14px;")
    box = QVBoxLayout(panel)
    box.setContentsMargins(16, 14, 16, 14)
    box.setSpacing(6)
    title = QLabel("Processus les plus gourmands (mémoire)")
    title.setStyleSheet(f"color: {_TEXT}; font-size: 14px; font-weight: 600;")
    box.addWidget(title)
    for row in processes[:6]:
        line = QLabel(f"{plain_label(row.get('name'), 32)}  ·  {row.get('value')} %")
        line.setStyleSheet(f"color: {_MUTED}; font-size: 13px;")
        box.addWidget(line)
    return panel


def make_metrics_dashboard(
    snapshot: dict[str, Any],
    cpu_series: Sequence[dict[str, Any]],
    mem_series: Sequence[dict[str, Any]],
    processes: Sequence[dict[str, Any]] = (),
    period: str = "",
    on_period_change=None,
    parent: QWidget | None = None,
) -> QWidget:
    """Machine-activity dashboard: live snapshot, CPU/memory history, top procs."""
    root = QWidget(parent)
    root.setObjectName("metricsDashboard")
    root.setStyleSheet(
        f"#metricsDashboard {{ background: {_BG}; }}"
        f"QLabel {{ color: {_TEXT}; }}"
        f"QLabel#sub {{ color: {_MUTED}; font-size: 13px; }}"
    )
    layout = QVBoxLayout(root)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    heading = QLabel("Activité machine")
    heading.setStyleSheet("font-size: 19px; font-weight: 600;")
    layout.addWidget(heading)

    if on_period_change is not None:
        layout.addWidget(_period_bar(period, on_period_change, METRIC_PERIODS))

    if snapshot:
        battery = ""
        if snapshot.get("battery") is not None:
            battery = f" · batterie {snapshot['battery']:.0f} %"
        sub = QLabel(
            f"Maintenant · CPU {snapshot.get('cpu', 0):.0f} % · "
            f"mémoire {snapshot.get('mem', 0):.0f} % · "
            f"disque {snapshot.get('disk', 0):.0f} %{battery}"
        )
        sub.setObjectName("sub")
        layout.addWidget(sub)

    label = {"1h": "1 h", "6h": "6 h", "24h": "24 h", "7d": "7 j"}.get(period, "24 h")
    if cpu_series:
        layout.addWidget(_line_chart(f"Processeur ({label})", cpu_series, _ACCENTS[0], "% CPU"), 1)
    if mem_series:
        layout.addWidget(_line_chart(f"Mémoire ({label})", mem_series, _ACCENTS[1], "% mémoire"), 1)
    if not cpu_series and not mem_series:
        note = QLabel("L'historique se remplit pendant que Jarvis tourne. "
                      "Reviens dans quelques minutes pour voir les courbes.")
        note.setObjectName("sub")
        note.setWordWrap(True)
        layout.addWidget(note)

    if processes:
        layout.addWidget(_process_panel(processes))

    if not cpu_series and not mem_series and not processes:
        layout.addStretch(1)

    return root


# Period presets offered by each dashboard's selector.
USAGE_PERIODS = (("today", "Aujourd'hui"), ("7d", "7 j"), ("30d", "30 j"), ("all", "Tout"))
METRIC_PERIODS = (("1h", "1 h"), ("6h", "6 h"), ("24h", "24 h"), ("7d", "7 j"))


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
) -> QWidget:
    """Build the token-usage dashboard widget from aggregated payloads."""
    root = QWidget(parent)
    root.setObjectName("usageDashboard")
    root.setStyleSheet(
        f"#usageDashboard {{ background: {_BG}; }}"
        f"QLabel {{ color: {_TEXT}; }}"
        f"QLabel#sub {{ color: {_MUTED}; font-size: 13px; }}"
    )
    layout = QVBoxLayout(root)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    heading = QLabel("Consommation de tokens")
    heading.setStyleSheet("font-size: 19px; font-weight: 600;")
    layout.addWidget(heading)

    if on_period_change is not None:
        layout.addWidget(_period_bar(period, on_period_change))

    if overview:
        sub = QLabel(
            f"{overview.get('period', '').capitalize()} · "
            f"{_human(overview.get('output', 0))} générés · "
            f"{_human(overview.get('input', 0))} en entrée · "
            f"{_human(overview.get('cache_read', 0))} en cache · "
            f"{overview.get('sessions', 0)} sessions"
        )
        sub.setObjectName("sub")
        layout.addWidget(sub)

    cost = sum(r.get("est_cost_usd", 0) or 0 for r in model_rows)
    if cost:
        amount = f"{cost:,.2f}".replace(",", " ").replace(".", ",")
        cost_label = QLabel(f"Coût estimé équivalent API : {amount} $ "
                            "(indicatif ; l'abonnement n'est pas facturé au token)")
        cost_label.setObjectName("sub")
        layout.addWidget(cost_label)

    if trend_series:
        cats = [_short_day(d["day"]) for d in trend_series]
        vals = [_millions(d["total_tokens"]) for d in trend_series]
        layout.addWidget(_bar_chart("Tokens par jour", cats, vals, _ACCENTS, "M tokens"), 1)

    if model_rows:
        cats = [r["model"].replace("claude-", "") for r in model_rows]
        vals = [_millions(r["total_tokens"]) for r in model_rows]
        layout.addWidget(_bar_chart("Par modèle", cats, vals, _ACCENTS[1:], "M tokens"), 1)

    if project_rows:
        cats = [plain_label(r["project"]) for r in project_rows]
        vals = [_millions(r["total_tokens"]) for r in project_rows]
        layout.addWidget(_bar_chart("Par projet", cats, vals, _ACCENTS[2:], "M tokens"), 1)

    return root


def plain_label(text: str, limit: int = 14) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


class _UsageLoader(QObject):
    """Pulls the aggregates off the UI thread (a cold index pass takes a few
    seconds, which must never freeze the window)."""

    done = Signal(dict, list, list, list, str)
    failed = Signal(str)

    def __init__(self, period: str = "30d"):
        super().__init__()
        self.period = period

    def run(self) -> None:
        try:
            from jarvis.capabilities.usage import UsageCapability

            cap = UsageCapability()
            overview = cap.overview(self.period).data
            trend = cap.trend(14).data.get("series", [])
            models = cap.by_model(self.period).data.get("models", [])
            projects = cap.by_project(self.period, 6).data.get("projects", [])
        except Exception as error:  # pragma: no cover - defensive
            self.failed.emit(str(error))
            return
        self.done.emit(overview, trend, models, projects, self.period)


class UsageWindow(QMainWindow):
    """Standalone token-usage dashboard window, loaded asynchronously."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Jarvis · Consommation de tokens")
        self.resize(820, 760)
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
                  projects: list, period: str) -> None:
        self.setCentralWidget(make_usage_dashboard(
            overview, trend, models, projects, period, self._on_period, self))

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
            procs = cap.top_processes("memory", 6).data.get("processes", [])
        except Exception as error:  # pragma: no cover - defensive
            self.failed.emit(str(error))
            return
        self.done.emit(snapshot, cpu, mem, procs, self.period)


class MetricsWindow(QMainWindow):
    """Standalone machine-activity dashboard window, loaded asynchronously."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Jarvis · Activité machine")
        self.resize(820, 780)
        self.setStyleSheet(f"QMainWindow {{ background: {_BG}; }}")
        self._thread: QThread | None = None
        self._loader: _MetricsLoader | None = None
        self._period = "24h"
        self.reload()

    def reload(self, period: str | None = None) -> None:
        if period:
            self._period = period
        if self._thread is not None and self._thread.isRunning():
            return
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
                  procs: list, period: str) -> None:
        self.setCentralWidget(make_metrics_dashboard(
            snapshot, cpu, mem, procs, period, self._on_period, self))

    def _show_error(self, message: str) -> None:
        label = QLabel(f"Activité machine indisponible.\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {_MUTED}; font-size: 14px;")
        self.setCentralWidget(label)
