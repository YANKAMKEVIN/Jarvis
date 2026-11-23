"""Dashboard tab « Journal »: what the local activity journal holds, filterable and erasable.

The journal keeps tool names, wake words and alerts for 30 days, never the
arguments or the words spoken. This tab only reads that local file.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

DAY = 24 * 3600
PERIODS = (("Aujourd'hui", "today"), ("7 derniers jours", "7d"), ("30 derniers jours", "30d"))
KINDS = (("Tout", ""), ("Outils", "tool"), ("Réveils « Jarvis »", "wake"), ("Alertes", "alert"))
LEVELS = (("Tous les résultats", ""), ("Réussis", "ok"), ("Échecs", "error"), ("Refusés (mode sécurité)", "refused"))
KIND_TEXT = {"tool": "Outil", "wake": "Réveil", "alert": "Alerte"}
LEVEL_TEXT = {"ok": "réussi", "error": "échec", "refused": "refusé"}


def period_start(key: str, now: float) -> float:
    if key == "today":
        return time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    return now - (7 if key == "7d" else 30) * DAY


class JournalPage(QWidget):
    def __init__(self, store=None, clock=time.time, confirm=None, parent=None):
        super().__init__(parent)
        if store is None:
            from jarvis.activity import default_store
            store = default_store()
        self.store, self.clock = store, clock
        self.confirm = confirm or self._ask
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Journal local d'activité · 30 jours · noms d'outils, réveils et alertes, jamais vos paroles."))
        filters = QHBoxLayout()
        self.period, self.kind, self.level = QComboBox(), QComboBox(), QComboBox()
        for combo, options, name in ((self.period, PERIODS, "Période"), (self.kind, KINDS, "Type d'événement"),
                                     (self.level, LEVELS, "Résultat")):
            for title, value in options:
                combo.addItem(title, value)
            combo.setAccessibleName(name)
            combo.currentIndexChanged.connect(self.reload)
            filters.addWidget(combo)
        self.erase = QPushButton("Effacer cette période")
        self.erase.setAccessibleName("Effacer les événements de la période et du type affichés")
        self.erase.clicked.connect(self.erase_period)
        filters.addWidget(self.erase)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Quand", "Type", "Nom", "Résultat"])
        self.table.setAccessibleName("Événements du journal")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.reload()

    def _range(self):
        return period_start(self.period.currentData(), self.clock())

    def reload(self, *_):
        try:
            rows = self.store.query(kind=self.kind.currentData() or None, since=self._range(),
                                    level=self.level.currentData() or None, limit=500)
        except Exception:  # noqa: BLE001 - a busy or missing file is shown, never raised in Qt
            self.table.setRowCount(0)
            self.status.setText("Journal local indisponible.")
            return
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (time.strftime("%d/%m %H:%M", time.localtime(row["ts"])), KIND_TEXT.get(row["kind"], row["kind"]),
                      row["name"], LEVEL_TEXT.get(row.get("level") or "", "—"))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(index, column, item)
        self.status.setText(f"{len(rows)} événement(s) affiché(s)" + (" (500 au plus)" if len(rows) == 500 else "") + ".")

    def _ask(self, text):
        return QMessageBox.question(self, "Effacer le journal", text) == QMessageBox.StandardButton.Yes

    def erase_period(self):
        kind = self.kind.currentData() or None
        label = f"{self.period.currentText().lower()} ({self.kind.currentText().lower()})"
        if not self.confirm(f"Effacer définitivement les événements : {label} ?"):
            return 0
        try:
            removed = self.store.delete_range(self._range(), kind=kind)
        except Exception:  # noqa: BLE001
            self.status.setText("Effacement impossible : journal occupé. Réessayez.")
            return 0
        self.reload()
        self.status.setText(f"{removed} événement(s) effacé(s).")
        return removed
