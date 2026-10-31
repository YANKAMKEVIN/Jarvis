import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtCharts")

from PySide6.QtWidgets import QApplication, QLabel, QProgressBar

from jarvis.desktop import dashboard
from jarvis.desktop.dashboard import (
    DAY, TABS, DashboardWindow, ago, duration, make_alerts_dashboard, make_jarvis_dashboard,
    pretty_tool,
)

NOW = 2_000_000_000.0


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _texts(widget):
    return [label.text() for label in widget.findChildren(QLabel)]


def test_ago_and_pretty_tool():
    assert ago(10) == "à l'instant"
    assert ago(5 * 60) == "il y a 5 min"
    assert ago(3 * 3600) == "il y a 3 h"
    assert ago(DAY + 5) == "hier"
    assert ago(4 * DAY) == "il y a 4 j"
    assert pretty_tool("open_app_and_type") == "Open app and type"
    assert pretty_tool("") == ""
    assert duration(0.2) == "< 1 min"
    assert duration(42) == "42 min"
    assert duration(1463) == "24 h 23"
    assert duration(120) == "2 h"


def test_jarvis_tab_shows_missions_tools_wakes_and_sessions(app):
    missions = [
        {"at": NOW - 600, "goal": "Résumer mes mails", "status": "completed", "step_count": 3},
        {"at": NOW - 7200, "goal": "Ranger le bureau", "status": "failed", "step_count": 1},
        {"at": NOW - 30 * DAY, "goal": "Vieille mission", "status": "completed", "step_count": 2},
    ]
    tools = [{"name": "get_time", "count": 12}, {"name": "open_app", "count": 4}]
    counts = {"tools_today": 5, "tools_week": 16, "wakes_today": 2, "wakes_week": 9,
              "alerts_week": 1}
    sessions = [{"project": "Jarvis", "total_tokens": 2_500_000, "duration_min": 42,
                 "last_ts": NOW - 3600}]
    widget = make_jarvis_dashboard(missions, tools, counts, sessions, now=NOW)
    texts = _texts(widget)
    # Only the two missions of the week count; one in two succeeded.
    assert "2" in texts and "50 % réussies" in texts
    assert "9" in texts and "2 aujourd'hui" in texts
    assert "Résumer mes mails" in texts
    assert any("échouée" in t for t in texts)
    assert "Get time" in texts and "12 fois" in texts
    assert len(widget.findChildren(QProgressBar)) == 2
    assert "Jarvis" in texts
    assert any(t.endswith("tokens · 42 min · il y a 1 h") for t in texts)


def test_jarvis_tab_empty_explains_what_will_appear(app):
    widget = make_jarvis_dashboard([], [], {}, [], now=NOW)
    texts = " ".join(_texts(widget))
    assert "Aucune mission pour l'instant" in texts
    assert "s'afficheront ici" in texts
    assert "Aucune session Claude" in texts
    assert widget.findChildren(QProgressBar) == []


def test_alerts_tab_counts_and_lists_newest_first(app):
    alerts = [
        {"ts": NOW - 120, "name": "Mémoire", "detail": "Mémoire à 92 %", "level": "warning"},
        {"ts": NOW - 2 * DAY, "name": "Mémoire", "detail": "Mémoire à 90 %", "level": "warning"},
        {"ts": NOW - 3 * DAY, "name": "Tokens", "detail": "Journée chargée", "level": "info"},
        {"ts": NOW - 20 * DAY, "name": "Disque", "detail": "", "level": "warning"},
    ]
    widget = make_alerts_dashboard(alerts, now=NOW)
    texts = _texts(widget)
    assert "1" in texts and "3" in texts  # 24 h / 7 j
    assert "il y a 2 min" in texts and "Mémoire" in texts  # latest alert card
    rows = [t for t in texts if " — " in t or t == "Disque"]
    assert rows[0] == "Mémoire — Mémoire à 92 %"
    assert "Disque" in texts  # still in the 30-day history


def test_alerts_tab_empty(app):
    widget = make_alerts_dashboard([], now=NOW)
    assert any("Aucune alerte enregistrée" in t for t in _texts(widget))


class _StubPage(dashboard.QMainWindow):
    built = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reloads = 0
        _StubPage.built.append(self)

    def reload(self, *a, **k):
        self.reloads += 1


def test_window_builds_tabs_lazily_and_switches(app, monkeypatch):
    _StubPage.built = []
    # Swap every page factory for a stub before the first tab is built.
    monkeypatch.setattr(dashboard, "JarvisPage", _StubPage)
    monkeypatch.setattr(dashboard, "AlertsPage", _StubPage)
    monkeypatch.setattr(dashboard, "UsageWindow", _StubPage)
    monkeypatch.setattr(dashboard, "MetricsWindow", _StubPage)
    window = DashboardWindow(tab="alerts")
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [l for _, l in TABS]
    assert window.tabs.currentIndex() == 3
    assert len(_StubPage.built) == 1 and window.page("jarvis") is None

    window.show_tab("metrics")
    assert window.tabs.currentIndex() == 2 and len(_StubPage.built) == 2
    window.show_tab("metrics")  # already built: not rebuilt
    assert len(_StubPage.built) == 2
    window.reload()
    assert window.page("metrics").reloads == 1
    window.show_tab("nope")  # unknown key falls back to the Jarvis tab
    assert window.tabs.currentIndex() == 0 and window.page("jarvis") is not None
    window.close()
