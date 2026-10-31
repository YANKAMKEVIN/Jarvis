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
    assert any("gourmandes" in t for t in labels)        # panel title
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


def test_unit_picks_readable_suffix():
    from jarvis.desktop.charts import _unit

    assert _unit([11_880_000_000, 3]) == (1e9, "Md")
    assert _unit([30_540_000]) == (1e6, "M")
    assert _unit([999]) == (1.0, "")


def test_fill_days_keeps_idle_days_as_zero():
    import datetime as dt
    from jarvis.desktop.charts import fill_days

    series = [{"day": "2026-10-16", "total_tokens": 5}, {"day": "2026-10-19", "total_tokens": 7}]
    filled = fill_days(series, 5, today=dt.date(2026, 10, 20))
    assert [d["day"] for d in filled] == [
        "2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19", "2026-10-20"]
    assert [d["total_tokens"] for d in filled] == [5, 0, 0, 7, 0]


def test_weekly_buckets_end_today():
    from jarvis.desktop.charts import weekly

    days = [{"day": f"d{i}", "total_tokens": 1} for i in range(10)]
    buckets = weekly(days)
    assert [b["total_tokens"] for b in buckets] == [3, 7]
    assert buckets[-1]["day"] == "d3"


def test_usage_dashboard_cards_show_change(app):
    import datetime as dt

    overview = {"period": "sur 7 jours", "output": 2_000_000, "input": 1,
                "cache_read": 9_000_000, "sessions": 4, "days": 3,
                "total_tokens": 12_000_000}
    trend = [{"day": "2026-10-20", "total_tokens": 12_000_000}]
    widget = make_usage_dashboard(overview, trend, [], period="7d",
                                  comparison={"previous": 6_000_000, "against": "vs avant"},
                                  today=dt.date(2026, 10, 20))
    texts = [l.text() for l in widget.findChildren(QLabel)]
    assert "12,0 M" in texts
    assert any("▲ 100 % vs avant" in t for t in texts)


def test_usage_dashboard_all_period_groups_by_week(app):
    import datetime as dt

    trend = [{"day": "2026-10-20", "total_tokens": 1_000_000}]
    widget = make_usage_dashboard({"period": "depuis le début"}, trend, [], period="all",
                                  today=dt.date(2026, 10, 20))
    titles = [l.text() for l in widget.findChildren(QLabel, "panelTitle")]
    assert titles == ["Tokens par semaine · M"]


def test_metrics_dashboard_groups_apps_and_flags_threshold(app):
    snapshot = {"cpu": 23.0, "mem": 93.0, "disk": 50.0, "mem_used": 15e9, "mem_total": 16e9}
    cpu = [{"ts": 1_700_000_000.0, "value": 20.0}, {"ts": 1_700_003_600.0, "value": 40.0}]
    apps = [{"name": "Google Chrome", "bytes": 3_200_000_000, "processes": 43, "value": 20.0}]
    widget = make_metrics_dashboard(snapshot, cpu, [], apps, period="24h")
    texts = [l.text() for l in widget.findChildren(QLabel)]
    assert "Google Chrome" in texts and "3,0 Go · 43 processus" in texts
    from jarvis.desktop.charts import _mem
    assert _mem(45 * 2**20) == "45 Mo"
    from PySide6.QtWidgets import QProgressBar
    (gauge,) = widget.findChildren(QProgressBar)
    assert gauge.value() == 1000  # the heaviest app fills its gauge
    assert "13,9 Go sur 14,9 Go" in texts
    (view,) = widget.findChildren(QChartView)
    assert len(view.chart().series()) == 2  # the curve and its dashed threshold


def test_pretty_model_and_updated_text():
    from jarvis.desktop.charts import pretty_model, updated_text

    assert pretty_model("claude-opus-5-5") == "Opus 5.5"
    assert pretty_model("claude-sonnet-5") == "Sonnet 5"
    assert pretty_model("claude-haiku-4-5-20251001") == "Haiku 4.5"
    assert updated_text(2) == "mis à jour à l'instant"
    assert updated_text(42) == "mis à jour il y a 42 s"
    assert updated_text(130) == "mis à jour il y a 2 min"


def test_usage_dashboard_marks_today_and_peak(app):
    import datetime as dt

    trend = [{"day": "2026-10-18", "total_tokens": 9_000_000},
             {"day": "2026-10-20", "total_tokens": 2_000_000}]
    models = [{"model": "claude-opus-5-5", "total_tokens": 9_000_000}]
    widget = make_usage_dashboard({"period": "x"}, trend, models, period="7d",
                                  today=dt.date(2026, 10, 20))
    (legend,) = widget.findChildren(QLabel, "panelLegend")
    assert "aujourd'hui" in legend.text() and "pic 18/10 · 9,0 M" in legend.text()
    daily, ranking = widget.findChildren(QChartView)
    (stacked,) = daily.chart().series()
    sets = stacked.barSets()
    assert [s.at(4) for s in sets] == [0, 9.0, 0]   # the peak (18/10) sits in its own layer
    assert [s.at(6) for s in sets] == [0, 0, 2.0]   # today too
    texts = [i.text() for i in ranking.chart().childItems() if hasattr(i, "text")]
    assert "9,0 M" in texts  # value written at the end of the bar, in the cards format
    assert ranking.chart().axes()[0].categories() == ["Opus 5.5"]


def test_metrics_dashboard_shows_update_time(app):
    import time as _time

    cpu = [{"ts": 1.0, "value": 20.0}, {"ts": 2.0, "value": 40.0}]
    widget = make_metrics_dashboard({"cpu": 1.0}, cpu, [], period="1h",
                                    on_period_change=lambda k: None,
                                    updated_at=_time.time() - 70)
    assert widget.findChild(QLabel, "updated").text() == "mis à jour il y a 1 min"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
