import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtCharts")

from PySide6.QtCharts import QChartView
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from jarvis.desktop.charts import (
    USAGE_PERIODS, make_metrics_dashboard, make_usage_dashboard,
    plain_label, _short_day, _millions,
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


def test_metrics_dashboard_with_processes_and_period(app):
    from jarvis.desktop.charts import METRIC_PERIODS

    snapshot = {"cpu": 23.0, "mem": 61.0, "disk": 78.0, "battery": 88.0}
    cpu = [{"ts": 1.0, "value": 20.0}, {"ts": 2.0, "value": 40.0}]
    procs = [{"name": "Chrome", "value": 25.0}, {"name": "Xcode", "value": 12.0}]
    clicks = []
    widget = make_metrics_dashboard(snapshot, cpu, [], procs,
                                    period="24h", on_period_change=clicks.append)
    labels = [l.text() for l in widget.findChildren(QLabel)]
    assert any("Chrome" in t for t in labels)           # process row rendered
    assert any("gourmands" in t for t in labels)         # process panel title
    buttons = [b for b in widget.findChildren(QPushButton)]
    assert len(buttons) == len(METRIC_PERIODS)
    buttons[0].click()
    assert clicks


def test_plain_label_truncates():
    assert plain_label("Jarvis") == "Jarvis"
    assert plain_label("UnTresLongNomDeProjet") == "UnTresLongNom…"


def test_usage_dashboard_with_projects_and_period(app):
    overview = {"period": "sur 30 jours", "output": 1, "input": 1,
                "cache_read": 1, "sessions": 5}
    trend = [{"day": "2026-10-20", "total_tokens": 1_000_000}]
    models = [{"model": "claude-opus-5-5", "total_tokens": 9_000_000, "est_cost_usd": 12.5}]
    projects = [{"project": "Alpha", "total_tokens": 5_000_000},
                {"project": "Beta", "total_tokens": 2_000_000}]
    clicks = []
    widget = make_usage_dashboard(overview, trend, models, projects,
                                  period="30d", on_period_change=clicks.append)
    # three charts: daily, model, project
    assert len(widget.findChildren(QChartView)) == 3
    # one period button per preset, the current one checked
    buttons = [b for b in widget.findChildren(QPushButton) if b.text() in dict(
        (lbl, key) for key, lbl in USAGE_PERIODS)]
    assert len(buttons) == len(USAGE_PERIODS)
    buttons[0].click()
    assert clicks  # clicking a period button fires the callback


def test_usage_dashboard_no_period_bar_without_callback(app):
    widget = make_usage_dashboard({"period": "x"}, [], [{"model": "m", "total_tokens": 1}])
    assert widget.findChildren(QPushButton) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
