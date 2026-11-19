"""UI/UX refinements of the desktop window; simulated worker, no model/network/macOS actions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import Controller, DesktopShell, STYLE


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyleSheet(STYLE)
    return instance


class Settings:
    def __init__(self): self.values = {}
    def value(self, key, default=None): return self.values.get(key, default)
    def setValue(self, key, value): self.values[key] = value


@pytest.fixture
def shell(app, monkeypatch):
    monkeypatch.setattr("jarvis.desktop.app.QSystemTrayIcon.isSystemTrayAvailable", lambda: False)
    controller = Controller()
    controller.reduced_motion = True
    instance = DesktopShell(app, controller, settings=Settings())
    yield instance
    instance.finish_transfer()
    for window in (instance.full, instance.compact, instance.orb_window):
        window.hide()


def listen(controller, state="listening"):
    controller.voice_worker = Mock()
    controller.voice_event({"type": "state", "state": state, "mic_open": True})


def test_voice_shortcuts_follow_the_session_and_pages_have_their_own(shell):
    c, window = shell.controller, shell.full
    assert not window.interrupt_shortcut.isEnabled() and not window.mic_shortcut.isEnabled()
    listen(c, "speaking")
    assert window.interrupt_shortcut.isEnabled() and window.mic_shortcut.isEnabled()
    window.interrupt_shortcut.activated.emit()
    c.voice_worker.interrupt.assert_called_once_with()
    window.mic_shortcut.activated.emit()
    c.voice_worker.set_muted.assert_called_once_with(True)
    assert "Échap" in window.assistant.interrupt_button.text()
    assert window.assistant.mic_button.text().endswith("· M")
    for index, shortcut in enumerate(window.page_shortcuts):
        shortcut.activated.emit()
        assert window.pages.currentIndex() == index
    c.voice_event({"type": "state", "state": "error", "message": "Connexion perdue."})
    assert not window.interrupt_shortcut.isEnabled() and not window.mic_shortcut.isEnabled()


def test_mission_timeline_orders_done_steps_before_the_one_under_way():
    from jarvis.desktop.presentation import mission_progress, mission_timeline, project_task
    task = project_task({'id': 'm', 'objective': 'Préparer la réunion', 'status': 'running', 'current_tool': 'web_answer',
                         'steps': [{'tool': 'list_calendar_events', 'ok': True}, {'tool': 'open_app', 'ok': False},
                                   {'tool': 'search_notes', 'ok': True, 'state_confirmed': True}]})
    rows = mission_timeline(task)
    assert [row['kind'] for row in rows] == ['done', 'error', 'done', 'running']
    assert rows[-1]['text'].startswith('En cours · ')
    assert [row['kind'] for row in mission_timeline(task, limit=1)] == ['done', 'running']
    assert mission_progress(task) == 'Étape 4 en cours'
    finished = {**task, 'status': 'completed', 'current': ''}
    assert [row['kind'] for row in mission_timeline(finished)] == ['done', 'error', 'done']
    assert mission_progress(finished) == '3 étapes traitées'
    assert mission_progress({**finished, 'step_count': 1}) == '1 étape traitée'
    queued = project_task({'id': 'q', 'status': 'queued', 'steps': []})
    assert [row['kind'] for row in mission_timeline(queued)] == ['idle']
    waiting = project_task({'id': 'w', 'status': 'needs_confirmation', 'steps': [{'tool': 'open_app', 'ok': True}]})
    assert [row['kind'] for row in mission_timeline(waiting)] == ['done', 'waiting']


def test_mission_card_shows_a_step_rail_and_a_distinct_cancel_action(shell, app):
    from jarvis.desktop.presentation import project_task
    c = shell.controller
    shell.show_full()
    listen(c)
    c.voice_event(project_task({'id': 'm', 'objective': 'Préparer la réunion', 'status': 'running', 'current_tool': 'web_answer',
                                'steps': [{'tool': 'list_calendar_events', 'ok': True}, {'tool': 'open_app', 'ok': False}]}))
    app.processEvents()
    deck = shell.full.assistant.mission
    assert [p.isVisible() for p in deck.panels] == [True, False]
    panel = deck.panels[0]
    assert [row.marker.kind for row in panel.steps if row.isVisible()] == ['done', 'error']
    assert panel.current.isVisible() and panel.current.marker.kind == 'running'
    assert 'ÉTAPE 3 EN COURS' in panel.heading.text()
    assert panel.cancel.objectName() == 'cancelMission' and panel.details.objectName() != 'cancelMission'
    shell.full.navigate(2)
    from jarvis.desktop.mission_panel import StepRow
    rows = shell.full.activity.findChildren(StepRow)
    assert [row.marker.kind for row in rows] == ['done', 'error', 'running']
