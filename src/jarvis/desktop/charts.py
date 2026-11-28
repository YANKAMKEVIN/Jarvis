"""QtCharts panels for Jarvis introspection (token usage and machine metrics).
Pure view code: it takes already-aggregated series (the dicts the capabilities
return) and renders them. No data access here, so it stays testable off a fixed
payload and reusable for any series. The windows below load the data on a
background thread and hand it to the builders of charts_dashboards (built on
charts_cards, charts_widgets and charts_format, all re-exported here).
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
from jarvis.desktop.charts_format import (  # noqa: F401 -- re-exported
    _short_day,
    _millions,
    _unit,
    fill_days,
    weekly,
    _every_other,
    _gb,
    _mem,
    _money,
    pretty_model,
    updated_text,
    plain_label,
    _long_day,
    _delta,
    _comparison,
    _BG,
    _PANEL,
    _TEXT,
    _MUTED,
    _UP,
    _DOWN,
    _ALERT,
    _TODAY,
    _PEAK,
    _ACCENTS,
    USAGE_PERIODS,
    METRIC_PERIODS,
    TREND_DAYS,
    _WEEKLY_AFTER,
    METRICS_REFRESH_MS,
    _UNITS,
    _MONTHS,
)
from jarvis.desktop.charts_widgets import (  # noqa: F401 -- re-exported
    _show_tip,
    _style_chart,
    _small_font,
    _style_axes,
    _value_axis,
    _view,
    _panel,
    _swatch,
    _daily_chart,
    _ranking_chart,
    _line_chart,
)
from jarvis.desktop.charts_cards import (  # noqa: F401 -- re-exported
    _stat_card,
    _cards_row,
    _usage_cards,
    _metrics_cards,
    _gauges,
    _apps_list,
    _dashboard_root,
    _period_bar,
)
from jarvis.desktop.charts_dashboards import (  # noqa: F401 -- re-exported
    make_metrics_dashboard,
    make_usage_dashboard,
)


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
