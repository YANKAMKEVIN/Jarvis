import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtCharts")

from PySide6.QtCharts import QChartView
from PySide6.QtWidgets import QApplication

from jarvis.desktop.charts import (
    make_metrics_dashboard, make_usage_dashboard, _short_day, _millions,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_short_day_and_millions():
    assert _short_day("2026-10-16") == "16/10"
    assert _short_day("weird") == "weird"
    assert _millions(30_540_000) == 30.54


def test_dashboard_builds_two_charts(app):
    overview = {"period": "sur 30 jours", "output": 30_540_000, "input": 60_000,
                "cache_read": 5_000_000_000, "sessions": 53}
    trend = [{"day": "2026-10-19", "total_tokens": 1_200_000_000},
             {"day": "2026-10-20", "total_tokens": 350_000_000}]
    models = [{"model": "claude-opus-5-5", "total_tokens": 10_000_000_000},
              {"model": "claude-sonnet-5", "total_tokens": 40_000_000}]
    widget = make_usage_dashboard(overview, trend, models)
    views = widget.findChildren(QChartView)
    assert len(views) == 2  # daily + by-model


def test_dashboard_tolerates_empty_series(app):
    widget = make_usage_dashboard({}, [], [])
    assert widget.findChildren(QChartView) == []


def test_metrics_dashboard_builds_two_lines(app):
    snapshot = {"cpu": 23.0, "mem": 61.0, "disk": 78.0, "battery": 88.0}
    cpu = [{"ts": 1.0, "value": 20.0}, {"ts": 2.0, "value": 40.0}]
    mem = [{"ts": 1.0, "value": 55.0}, {"ts": 2.0, "value": 60.0}]
    widget = make_metrics_dashboard(snapshot, cpu, mem)
    assert len(widget.findChildren(QChartView)) == 2


def test_metrics_dashboard_empty_shows_note_not_charts(app):
    widget = make_metrics_dashboard({}, [], [])
    assert widget.findChildren(QChartView) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
