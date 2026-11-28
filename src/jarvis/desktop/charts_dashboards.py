"""Token-usage and machine-metrics dashboards assembled from cards and charts."""
from __future__ import annotations

import datetime as dt
import time
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
from typing import Any, Sequence

from jarvis.capabilities.usage import _human
from jarvis.desktop.charts_cards import (
    _apps_list,
    _dashboard_root,
    _metrics_cards,
    _period_bar,
    _usage_cards,
)
from jarvis.desktop.charts_format import (
    METRIC_PERIODS,
    TREND_DAYS,
    _ACCENTS,
    _ALERT,
    _MUTED,
    _PEAK,
    _TODAY,
    _WEEKLY_AFTER,
    _every_other,
    _long_day,
    _short_day,
    _unit,
    fill_days,
    plain_label,
    pretty_model,
    updated_text,
    weekly,
)
from jarvis.desktop.charts_widgets import (
    _daily_chart,
    _line_chart,
    _panel,
    _ranking_chart,
    _swatch,
)
from jarvis.insights.detector import Thresholds


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
