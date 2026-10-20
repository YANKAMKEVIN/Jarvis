"""QtCharts panels for Jarvis introspection (token usage, and later machine
metrics). Pure view code: it takes already-aggregated series (the dicts the
usage capability returns) and renders them. No data access here, so it stays
testable off a fixed payload and reusable for any series.
"""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QValueAxis,
)
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

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


def make_usage_dashboard(
    overview: dict[str, Any],
    trend_series: Sequence[dict[str, Any]],
    model_rows: Sequence[dict[str, Any]],
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

    if trend_series:
        cats = [_short_day(d["day"]) for d in trend_series]
        vals = [_millions(d["total_tokens"]) for d in trend_series]
        layout.addWidget(_bar_chart("Tokens par jour", cats, vals, _ACCENTS, "M tokens"), 1)

    if model_rows:
        cats = [r["model"].replace("claude-", "") for r in model_rows]
        vals = [_millions(r["total_tokens"]) for r in model_rows]
        layout.addWidget(_bar_chart("Par modèle", cats, vals, _ACCENTS[1:], "M tokens"), 1)

    return root


class _UsageLoader(QObject):
    """Pulls the aggregates off the UI thread (a cold index pass takes a few
    seconds, which must never freeze the window)."""

    done = Signal(dict, list, list)
    failed = Signal(str)

    def run(self) -> None:
        try:
            from jarvis.capabilities.usage import UsageCapability

            cap = UsageCapability()
            overview = cap.overview("30d").data
            trend = cap.trend(14).data.get("series", [])
            models = cap.by_model("30d").data.get("models", [])
        except Exception as error:  # pragma: no cover - defensive
            self.failed.emit(str(error))
            return
        self.done.emit(overview, trend, models)


class UsageWindow(QMainWindow):
    """Standalone token-usage dashboard window, loaded asynchronously."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Jarvis · Consommation de tokens")
        self.resize(800, 720)
        self.setStyleSheet(f"QMainWindow {{ background: {_BG}; }}")
        self._thread: QThread | None = None
        self._loader: _UsageLoader | None = None
        self.reload()

    def reload(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        placeholder = QLabel("Chargement du graphe…")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet(f"color: {_MUTED}; font-size: 15px;")
        self.setCentralWidget(placeholder)

        self._thread = QThread(self)
        self._loader = _UsageLoader()
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.done.connect(self._populate)
        self._loader.failed.connect(self._show_error)
        self._loader.done.connect(self._thread.quit)
        self._loader.failed.connect(self._thread.quit)
        self._thread.start()

    def _populate(self, overview: dict, trend: list, models: list) -> None:
        self.setCentralWidget(make_usage_dashboard(overview, trend, models, self))

    def _show_error(self, message: str) -> None:
        label = QLabel(f"Lecture de l'usage impossible.\n{message}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {_MUTED}; font-size: 14px;")
        self.setCentralWidget(label)
