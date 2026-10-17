"""Offscreen checks; no model, network or macOS actions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QElapsedTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from jarvis.desktop.app import Controller, DesktopShell, STYLE


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyleSheet(STYLE)
    return instance


def wait_until(app, predicate):
    timer = QElapsedTimer()
    timer.start()
    while not predicate() and timer.elapsed() < 3000:
        app.processEvents()
        QTest.qWait(10)
    assert predicate()


def test_two_views_share_draft_confirmation_and_result(app, monkeypatch):
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)
    controller = Controller(demo=True)
    shell = DesktopShell(app, controller)
    shell.show_full()
    suggestions = [b for b in shell.full.findChildren(QPushButton) if b.objectName() == "suggestion"]
    suggestions[0].click()
    assert controller.session.draft == "Ouvre Safari"
    assert not controller.session.turns and not controller.workers
    shell.switch_view()
    idle_height = shell.compact.height()
    assert shell.compact.conversation.input.text() == "Ouvre Safari"
    controller.submit()
    controller.submit()  # A second activation must not dispatch twice.
    wait_until(app, lambda: controller.session.pending is not None and not controller.workers)
    assert len(controller.session.turns) == 1
    wait_until(app, lambda: shell.compact.height() > idle_height)
    visible_confirmations = [b for b in shell.compact.findChildren(QPushButton)
                             if b.text() == "Confirmer" and b.isVisibleTo(shell.compact)]
    assert visible_confirmations
    shell.switch_view()
    assert shell.full.isVisible() and not shell.compact.isVisible()
    assert not shell.full.conversation.input.isEnabled()
    confirmations = [b for b in shell.full.findChildren(QPushButton) if b.text() == "Confirmer"]
    assert confirmations
    confirmations[-1].click()
    wait_until(app, lambda: not controller.session.busy and not controller.workers)
    assert controller.session.pending is None
    assert "Aucune application" in controller.session.turns[-1].reply
    assert shell.full.conversation.input.isEnabled()
    shell.full.hide()
    shell.compact.hide()


def test_cancel_and_clear_are_reflected_in_both_views(app, monkeypatch):
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)
    controller = Controller(demo=True)
    shell = DesktopShell(app, controller)
    controller.set_draft("essai")
    controller.submit()
    wait_until(app, lambda: controller.session.pending is not None and not controller.workers)
    controller.cancel()
    assert controller.session.turns[-1].status == "cancelled"
    assert shell.full.clear_button.isEnabled()
    controller.clear()
    assert not controller.session.turns
    assert shell.compact.conversation.input.text() == ""
    controller.reduced_motion = True
    controller.changed.emit()
    assert not shell.full.conversation.orb.timer.isActive()
    assert shell.full.conversation.opacity.opacity() == 1.0
    assert shell.full.conversation.fade.state().name == "Stopped"
    shell.full.hide()
    shell.compact.hide()
