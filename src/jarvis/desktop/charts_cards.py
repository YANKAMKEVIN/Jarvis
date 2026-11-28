"""Stat cards, gauges, app lists and period bar of the introspection dashboards."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from typing import Any, Sequence

from jarvis.capabilities.usage import _human
from jarvis.desktop.charts_format import (
    USAGE_PERIODS,
    _ACCENTS,
    _ALERT,
    _BG,
    _MUTED,
    _PANEL,
    _TEXT,
    _delta,
    _gb,
    _mem,
    _money,
    plain_label,
)
from jarvis.insights.detector import Thresholds


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


def _gauges(rows: Sequence[tuple[str, float, str]]) -> QWidget:
    """One gauge per (name, weight, amount text) row, its length relative to
    the heaviest row."""
    body = QWidget()
    grid = QGridLayout(body)
    grid.setContentsMargins(0, 4, 4, 2)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(8)
    grid.setColumnStretch(1, 1)
    top = max((weight for _, weight, _ in rows), default=0) or 1
    for i, (label, weight, amount) in enumerate(rows):
        name = QLabel(plain_label(label, 26))
        name.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
        gauge = QProgressBar()
        gauge.setObjectName("appGauge")
        gauge.setRange(0, 1000)
        gauge.setValue(int(weight / top * 1000))
        gauge.setTextVisible(False)
        gauge.setFixedHeight(8)
        gauge.setStyleSheet(
            "#appGauge { background: #1b2a3d; border: none; border-radius: 4px; }"
            f"#appGauge::chunk {{ background: {_ACCENTS[i % 3]}; border-radius: 4px; }}")
        value = QLabel(amount)
        value.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(name, i, 0)
        grid.addWidget(gauge, i, 1)
        grid.addWidget(value, i, 2)
    return body


def _apps_list(apps: Sequence[dict[str, Any]]) -> QWidget:
    """One gauge per app, its length relative to the heaviest app."""
    rows = []
    for row in apps[:6]:
        if row.get("bytes"):
            count = row.get("processes", 0)
            amount = _mem(row["bytes"]) + (f" · {count} processus" if count > 1 else "")
        else:  # plain per-process rows (value = % of memory)
            amount = f"{row.get('value')} %"
        rows.append((row.get("name"), row.get("bytes") or row.get("value") or 0, amount))
    return _gauges(rows)


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
