"""Every focusable control of the main windows has an accessible name (idea 46).

VoiceOver reads a button or checkbox by its text; other controls (lists,
fields, sliders, tables, icon buttons) need setAccessibleName.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QAbstractScrollArea, QApplication, QComboBox, QLabel, QTabBar, QWidget

from jarvis.desktop.app import Controller, DesktopShell, STYLE


def nameless(root: QWidget):
    missing = []
    for widget in root.findChildren(QWidget):
        if widget.focusPolicy() == Qt.FocusPolicy.NoFocus or isinstance(widget, QTabBar):
            continue
        if widget.accessibleName().strip():
            continue
        if isinstance(widget, QLabel) and widget.text().strip():
            continue  # VoiceOver reads a label's text
        ancestor = widget.parent()
        while ancestor is not None and not isinstance(ancestor, QComboBox):
            ancestor = ancestor.parent()
        if ancestor is not None:
            continue  # the popup of a named combo box
        if isinstance(widget, QAbstractButton) and widget.text().strip() and any(ch.isalpha() for ch in widget.text()):
            continue
        if isinstance(widget, QAbstractScrollArea) and type(widget).__name__ in {"QScrollArea"}:
            continue  # plain layout container
        if widget.parent() is not None and type(widget.parent()).__name__ in {"QComboBox", "QAbstractSpinBox", "QScrollArea"}:
            continue
        if type(widget).__name__ in {"QComboBoxPrivateContainer", "QComboBoxListView", "QWidget", "QFrame", "QStackedWidget"}:
            continue
        missing.append(f"{type(widget).__name__} {widget.objectName()!r} {getattr(widget, 'text', lambda: '')()!r}")
    return missing


@pytest.fixture
def shell(monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)

    class Settings:
        def __init__(self): self.values = {}
        def value(self, key, default=None): return self.values.get(key, default)
        def setValue(self, key, value): self.values[key] = value

    controller = Controller()
    shell = DesktopShell(app, controller, settings=Settings())
    yield shell
    shell.finish_transfer()
    for window in (shell.full, shell.compact, shell.orb_window):
        window.hide()


def test_main_windows_have_named_controls(shell):
    missing = nameless(shell.full) + nameless(shell.compact) + nameless(shell.orb_window)
    assert not missing, "\n".join(missing)


def test_dashboard_pages_have_named_controls(tmp_path):
    QApplication.instance() or QApplication([])
    from jarvis.activity import ActivityStore
    from jarvis.desktop.charts import make_metrics_dashboard, make_usage_dashboard
    from jarvis.desktop.dashboard import make_alerts_dashboard, make_jarvis_dashboard
    from jarvis.desktop.journal_page import JournalPage
    pages = [make_jarvis_dashboard([{"at": 0, "goal": "g", "status": "completed", "step_count": 1}],
                                   [{"name": "open_app", "count": 2}], {}),
             make_alerts_dashboard([]), make_usage_dashboard({}, [], []), make_metrics_dashboard({}, [], []),
             JournalPage(store=ActivityStore(tmp_path / "a.db"))]
    missing = [entry for page in pages for entry in nameless(page)]
    assert not missing, "\n".join(sorted(set(missing)))
