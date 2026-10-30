"""The single "Tableau de bord" window: one tab per view of Jarvis.

- Jarvis: what the assistant itself did (missions, tools, wakes, alerts) and
  the latest Claude Code sessions;
- Tokens and Machine: the two dashboards of `charts.py`, embedded as they are;
- Alertes: the history of the insights raised, kept across restarts.

Like `charts.py`, the builders are pure view code fed with plain payloads; the
loaders read the stores on a background thread.
"""

from __future__ import annotations

import time
from typing import Any, Sequence

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QMainWindow, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from jarvis.capabilities.usage import _human
from jarvis.desktop.charts import (
    METRICS_REFRESH_MS, MetricsWindow, UsageWindow, _ACCENTS, _ALERT, _BG, _MUTED, _PANEL,
    _TEXT, _UP, _cards_row, _dashboard_root, _gauges, _panel, _stat_card, _swatch,
    plain_label, updated_text,
)

DAY = 24 * 3600
WEEK = 7 * DAY

TABS = (("jarvis", "Jarvis"), ("usage", "Tokens"), ("metrics", "Machine"), ("alerts", "Alertes"))

# Mission statuses as the planner records them, in plain French.
_MISSION_STATUS = {
    "completed": ("terminée", _ACCENTS[1]),
    "failed": ("échouée", _ALERT),
    "cancelled": ("annulée", _MUTED),
    "needs_confirmation": ("attend ton accord", _UP),
    "needs_clarification": ("attend une précision", _UP),
}


def ago(seconds: float) -> str:
    """"il y a 5 min", "hier"… for lists of past events."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "à l'instant"
    if seconds < 3600:
        return f"il y a {seconds // 60} min"
    if seconds < DAY:
        return f"il y a {seconds // 3600} h"
    days = seconds // DAY
    return "hier" if days == 1 else f"il y a {days} j"


def duration(minutes: float) -> str:
    """42 → « 42 min », 1463 → « 24 h 23 »."""
    minutes = int(round(minutes or 0))
    if minutes < 1:
        return "< 1 min"
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d}" if rest else f"{hours} h"


def pretty_tool(name: str) -> str:
    """open_app_and_type → « Open app and type »: readable, still recognisable."""
    text = " ".join(str(name or "").replace("_", " ").split())
    return text[:1].upper() + text[1:]


def _rows_panel(title: str, rows: Sequence[tuple[str, str, str, str]], empty: str,
                legend: str = "") -> QFrame:
    """Panel listing (dot color, main text, side text, detail) rows."""
    body = QWidget()
    grid = QGridLayout(body)
    grid.setContentsMargins(0, 4, 4, 2)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(7)
    grid.setColumnStretch(1, 1)
    if not rows:
        note = QLabel(empty)
        note.setObjectName("sub")
        note.setWordWrap(True)
        grid.addWidget(note, 0, 0, 1, 3)
    for i, (color, main, side, detail) in enumerate(rows):
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 13px;")
        text = QLabel(main)
        text.setObjectName("rowText")
        text.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
        text.setToolTip(detail or main)
        when = QLabel(side)
        when.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        when.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(dot, i, 0)
        grid.addWidget(text, i, 1)
        grid.addWidget(when, i, 2)
    return _panel(title, body, legend)


def _scrolling(root: QWidget) -> QScrollArea:
    """Long lists stay readable in a short window instead of being squashed."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setStyleSheet(f"QScrollArea {{ background: {_BG}; border: none; }}")
    area.setWidget(root)
    return area


def make_jarvis_dashboard(
    missions: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]],
    counts: dict[str, int],
    sessions: Sequence[dict[str, Any]] = (),
    *,
    now: float | None = None,
    updated_at: float | None = None,
) -> QWidget:
    """What Jarvis did over the last 7 days.

    `missions`: rows of the mission history ({at, goal, status, step_count}),
    newest first. `tools`: {name, count} most used first. `counts`: tool calls
    today / 7 d, wakes today / 7 d, alerts 7 d. `sessions`: the usage store's
    recent Claude Code sessions.
    """
    now = time.time() if now is None else now
    root, layout = _dashboard_root("jarvisDashboard", "Ce que Jarvis a fait")
    sub = QLabel("Sur les 7 derniers jours" + (
        f" · {updated_text(now - updated_at)}" if updated_at is not None else ""))
    sub.setObjectName("sub")
    layout.addWidget(sub)

    week = [m for m in missions if now - (m.get("at") or 0) <= WEEK]
    done = sum(1 for m in week if m.get("status") == "completed")
    if week:
        rate = f"{round(done / len(week) * 100)} % réussies"
        tone = _ACCENTS[1] if done == len(week) else None
    else:
        rate, tone = "aucune cette semaine", None
    layout.addWidget(_cards_row([
        _stat_card("Missions", str(len(week)), rate, tone),
        _stat_card("Outils appelés", _human(counts.get("tools_week", 0)),
                   f"{counts.get('tools_today', 0)} aujourd'hui"),
        _stat_card("Réveils « Jarvis »", str(counts.get("wakes_week", 0)),
                   f"{counts.get('wakes_today', 0)} aujourd'hui"),
        _stat_card("Alertes", str(counts.get("alerts_week", 0)),
                   "voir l'onglet Alertes" if counts.get("alerts_week") else "rien à signaler"),
    ]))

    rows = []
    for m in missions[:8]:
        label, color = _MISSION_STATUS.get(m.get("status"), (m.get("status") or "?", _MUTED))
        steps = m.get("step_count") or 0
        side = f"{label} · {ago(now - (m.get('at') or now))}"
        detail = f"{m.get('goal')} — {label}" + (f", {steps} étape(s)" if steps else "")
        rows.append((color, plain_label(m.get("goal"), 70), side, detail))
    layout.addWidget(_rows_panel("Dernières missions", rows,
                                 "Aucune mission pour l'instant. Demande à Jarvis "
                                 "« lance une mission… » pour en voir ici."))

    if tools:
        gauge_rows = [(pretty_tool(t["name"]), t["count"],
                       f"{t['count']} fois") for t in tools[:8]]
        layout.addWidget(_panel("Outils les plus utilisés · 7 j", _gauges(gauge_rows)))
    else:
        layout.addWidget(_rows_panel("Outils les plus utilisés · 7 j", [],
                                     "Les outils appelés par la voix ou les missions "
                                     "s'afficheront ici."))

    session_rows = []
    for s in sessions[:6]:
        tokens = _human(s.get("total_tokens", 0))
        side = f"{tokens} tokens · {duration(s.get('duration_min'))} · {ago(now - (s.get('last_ts') or now))}"
        session_rows.append((_ACCENTS[2], plain_label(s.get("project") or "(sans projet)", 40),
                             side, s.get("project") or ""))
    layout.addWidget(_rows_panel("Dernières sessions Claude", session_rows,
                                 "Aucune session Claude Code trouvée."))
    layout.addStretch(1)
    return _scrolling(root)


def make_alerts_dashboard(alerts: Sequence[dict[str, Any]], *, now: float | None = None) -> QWidget:
    """History of the alerts raised ({ts, name, detail, level}), newest first."""
    now = time.time() if now is None else now
    root, layout = _dashboard_root("alertsDashboard", "Historique des alertes")
    day = sum(1 for a in alerts if now - a["ts"] <= DAY)
    week = [a for a in alerts if now - a["ts"] <= WEEK]
    latest = alerts[0] if alerts else None
    layout.addWidget(_cards_row([
        _stat_card("Dernières 24 h", str(day)),
        _stat_card("7 derniers jours", str(len(week))),
        _stat_card("Dernière alerte", ago(now - latest["ts"]) if latest else "—",
                   plain_label(latest["name"], 40) if latest else "aucune pour l'instant"),
    ]))
    rows = []
    for a in alerts:
        color = _ALERT if a.get("level") == "warning" else _ACCENTS[0]
        main = a["name"] + (f" — {a['detail']}" if a.get("detail") else "")
        rows.append((color, plain_label(main, 90), ago(now - a["ts"]), main))
    legend = "&nbsp;&nbsp;&nbsp;".join([_swatch(_ALERT, "à surveiller"),
                                        _swatch(_ACCENTS[0], "information")])
    layout.addWidget(_rows_panel("Alertes · 30 j", rows,
                                 "Aucune alerte enregistrée. Jarvis note ici chaque alerte "
                                 "machine ou tokens qu'il te signale.", legend if rows else ""))
    layout.addStretch(1)
    return _scrolling(root)


class _JarvisLoader(QObject):
    done = Signal(list, list, dict, list)
    failed = Signal(str)

    def run(self) -> None:
        try:
            from jarvis.activity import default_store
            from jarvis.capabilities.usage import UsageCapability
            from jarvis.memory.store import MemoryStore

            now = time.time()
            journal = default_store()
            missions = [{"at": m.at, "goal": m.goal, "status": m.status,
                         "step_count": m.step_count}
                        for m in MemoryStore().recent_missions(50)]
            tools = journal.top("tool", since=now - WEEK, limit=8)
            midnight = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
            counts = {
                "tools_today": journal.count("tool", since=midnight),
                "tools_week": journal.count("tool", since=now - WEEK),
                "wakes_today": journal.count("wake", since=midnight),
                "wakes_week": journal.count("wake", since=now - WEEK),
                "alerts_week": journal.count("alert", since=now - WEEK),
            }
            try:
                sessions = UsageCapability().recent_sessions(6).data.get("sessions", [])
            except Exception:
                sessions = []  # the Claude index is a bonus, never a blocker
        except Exception as error:  # pragma: no cover - defensive
            self.failed.emit(str(error))
            return
        self.done.emit(missions, tools, counts, sessions)


class _AlertsLoader(QObject):
    done = Signal(list)
    failed = Signal(str)

    def run(self) -> None:
        try:
            from jarvis.activity import default_store

            alerts = default_store().recent("alert", 100)
        except Exception as error:  # pragma: no cover - defensive
            self.failed.emit(str(error))
            return
        self.done.emit(alerts)


class _LoadedPage(QMainWindow):
    """A tab whose content is read off the UI thread, refreshed every 30 s
    while it is the visible tab."""

    loading_text = "Chargement…"
    error_text = "Lecture impossible."

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(f"QMainWindow {{ background: {_BG}; }}")
        self._thread: QThread | None = None
        self._loader: QObject | None = None
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

    def make_loader(self) -> QObject:
        raise NotImplementedError

    def reload(self, quiet: bool = False) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if not quiet:
            self.setCentralWidget(self._message(self.loading_text))
        self._thread = QThread(self)
        self._loader = self.make_loader()
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.done.connect(self._populate)
        self._loader.failed.connect(self._show_error)
        self._loader.done.connect(self._thread.quit)
        self._loader.failed.connect(self._thread.quit)
        self._thread.start()

    def _populate(self, *payload) -> None:
        raise NotImplementedError

    def _show_error(self, message: str) -> None:
        self.setCentralWidget(self._message(f"{self.error_text}\n{message}"))

    @staticmethod
    def _message(text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {_MUTED}; font-size: 15px;")
        return label


class JarvisPage(_LoadedPage):
    loading_text = "Lecture de l'activité de Jarvis…"
    error_text = "Activité de Jarvis indisponible."

    def make_loader(self) -> QObject:
        return _JarvisLoader()

    def _populate(self, missions: list, tools: list, counts: dict, sessions: list) -> None:
        now = time.time()
        self.setCentralWidget(make_jarvis_dashboard(missions, tools, counts, sessions,
                                                    now=now, updated_at=now))


class AlertsPage(_LoadedPage):
    loading_text = "Lecture des alertes…"
    error_text = "Historique des alertes indisponible."

    def make_loader(self) -> QObject:
        return _AlertsLoader()

    def _populate(self, alerts: list) -> None:
        self.setCentralWidget(make_alerts_dashboard(alerts))


class DashboardWindow(QMainWindow):
    """One window, four tabs. `show_tab(key)` opens it on a given view."""

    def __init__(self, parent: QWidget | None = None, tab: str = "jarvis"):
        super().__init__(parent)
        self.setWindowTitle("Jarvis · Tableau de bord")
        self.resize(940, 880)
        self.setStyleSheet(f"QMainWindow {{ background: {_BG}; }}")
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: {_BG}; top: 0; }}"
            f"QTabWidget::tab-bar {{ left: 10px; }}"
            f"QTabBar {{ background: {_BG}; }}"
            "QTabBar::tab { padding: 8px 18px; margin: 6px 2px 0 2px; border: none; "
            f"border-radius: 12px; color: {_MUTED}; background: transparent; font-size: 13px; }}"
            f"QTabBar::tab:selected {{ color: {_TEXT}; background: {_PANEL}; }}"
            f"QTabBar::tab:hover:!selected {{ color: {_TEXT}; }}"
        )
        self._pages: dict[str, QWidget] = {}
        self._factories = {"jarvis": JarvisPage, "usage": UsageWindow,
                           "metrics": MetricsWindow, "alerts": AlertsPage}
        for key, label in TABS:
            holder = QWidget()
            QVBoxLayout(holder).setContentsMargins(0, 0, 0, 0)
            holder.setObjectName(f"tab_{key}")
            self.tabs.addTab(holder, label)
        self.tabs.currentChanged.connect(self._ensure_current)
        self.setCentralWidget(self.tabs)
        self.show_tab(tab)

    def show_tab(self, key: str) -> None:
        keys = [k for k, _ in TABS]
        index = keys.index(key) if key in keys else 0
        if self.tabs.currentIndex() == index:
            self._ensure_current(index)
        else:
            self.tabs.setCurrentIndex(index)

    def page(self, key: str) -> QWidget | None:
        return self._pages.get(key)

    def reload(self) -> None:
        """Re-read the visible tab (the others refresh when they are shown)."""
        key = TABS[self.tabs.currentIndex()][0]
        page = self._pages.get(key)
        if page is not None:
            page.reload()

    def _ensure_current(self, index: int) -> None:
        # Pages are built on first view: opening the window on "Jarvis" never
        # pays for a cold token index.
        key = TABS[index][0]
        if key in self._pages:
            return
        page = self._factories[key]()
        page.setWindowFlags(Qt.WindowType.Widget)
        self.tabs.widget(index).layout().addWidget(page)
        self._pages[key] = page
