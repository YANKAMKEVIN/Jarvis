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


def test_voice_error_action_points_to_the_fix():
    from jarvis.desktop.recovery import voice_error_action
    assert voice_error_action("Clé Gemini manquante. Ajoutez GOOGLE_API_KEY dans le fichier .env") == ('api_key', 'Ajouter la clé API')
    assert voice_error_action("Choix audio enregistré invalide. Sélectionnez vos périphériques dans Réglages.")[0] == 'settings'
    assert voice_error_action("Connexion perdue.", can_reconnect=True) == ('retry', 'Reconnecter')
    assert voice_error_action("Le mot d’éveil local s’est arrêté. Relancez le vocal.") == ('retry', 'Réessayer')
    assert voice_error_action(None) == ('retry', 'Réessayer')


def test_voice_error_banner_names_the_cause_and_opens_the_right_place(shell, app):
    c, panel = shell.controller, shell.full.assistant
    shell.show_full()
    assert not panel.error_banner.isVisible()
    c.voice_event({'type': 'state', 'state': 'error',
                   'message': 'Choix audio enregistré invalide. Sélectionnez vos périphériques dans Réglages.'})
    assert panel.error_banner.isVisible() and 'Choix audio' in panel.error_text.text()
    assert panel.error_action.text() == 'Ouvrir Réglages' and panel.voice_notice.text() == ''
    panel.error_action.click()
    assert shell.full.pages.currentIndex() == 3
    shell.full.navigate(0)
    c.voice_event({'type': 'state', 'state': 'error', 'message': 'Connexion perdue.', 'retryable': True})
    assert panel.error_action.text() == 'Reconnecter'
    c.voice_event({'type': 'state', 'state': 'off'})
    assert not panel.error_banner.isVisible()


def test_suggestions_rotate_and_skip_refused_permissions():
    from jarvis.desktop.presentation import SUGGESTIONS, suggestions
    first = suggestions({}, 0)
    assert len(first) == 3 and first == [phrase for _, phrase in SUGGESTIONS[:3]]
    assert suggestions({}, 1) != first and suggestions({}, len(SUGGESTIONS)) == first
    refused = {'calendar': False, 'reminders': False, 'screen_recording': False, 'automation': False, 'accessibility': False}
    free = {phrase for permission, phrase in SUGGESTIONS if permission is None}
    for tick in range(6):
        assert set(suggestions(refused, tick)) <= free
    assert 'Quel est mon agenda demain ?' in suggestions({'calendar': True}, 0)
    assert 'Quel est mon agenda demain ?' in suggestions({'calendar': None}, 0)


def test_idle_assistant_suggests_requests_until_something_else_needs_the_space(shell, app):
    from jarvis.desktop.presentation import project_activity
    c, panel = shell.controller, shell.full.assistant
    shell.show_full()
    assert panel.suggestions.isVisible() and '« Quel est mon agenda demain ? »' in panel.suggestions.text()
    assert not panel.suggestion_timer.isActive()  # reduced motion: no rotation
    c.reduced_motion = False
    c.changed.emit()
    assert panel.suggestion_timer.isActive()
    before = panel.suggestions.text()
    panel.next_suggestions()
    assert panel.suggestions.text() != before
    listen(c)
    assert panel.suggestions.isVisible()
    c.voice_event(project_activity('get_volume', {'ok': True, 'volume': 40}, 'v'))
    assert not panel.suggestions.isVisible() and not panel.suggestion_timer.isActive()
    assert not shell.compact.findChildren(type(panel))


def test_sidebar_tools_open_the_existing_dashboard_history_memory_and_palette(shell, monkeypatch):
    opened = []
    monkeypatch.setattr(shell, 'show_dashboard', lambda tab='jarvis': opened.append(('dashboard', tab)))
    for name in ('history', 'memory', 'palette'):
        monkeypatch.setattr(shell.experience, name, lambda name=name: opened.append((name, None)))
    assert list(shell.full.tools) == ['dashboard', 'history', 'memory', 'palette']
    for tool in shell.full.tools.values():
        tool.click()
    assert opened == [('dashboard', 'jarvis'), ('history', None), ('memory', None), ('palette', None)]


def test_card_text_keeps_title_body_bullets_and_only_safe_sources():
    from jarvis.desktop.presentation import card_text
    entry = {'title': 'Réponse web', 'body': 'Deux heures de trajet.', 'items': ['Départ 6 h', 'Retour 21 h'],
             'sources': [{'title': 'SNCF', 'url': 'https://www.sncf-connect.com/train'},
                         {'title': 'Local', 'url': 'file:///etc/passwd'}]}
    assert card_text(entry) == ('Réponse web\n\nDeux heures de trajet.\n\n• Départ 6 h\n• Retour 21 h\n\n'
                                'Sources :\n1. SNCF — https://www.sncf-connect.com/train')
    assert card_text({'title': 'Volume', 'body': '', 'items': [], 'sources': []}) == 'Volume'


def test_card_copy_button_fills_the_clipboard_and_sources_become_chips(shell, app):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QPushButton
    from jarvis.desktop.presentation import project_activity
    c = shell.controller
    shell.show_full()
    c.voice_event(project_activity('web_answer', {'ok': True, 'external_knowledge_retrieved': True, 'message': 'Environ deux heures.',
        'sources': [{'title': 'SNCF', 'url': 'https://www.sncf-connect.com/train'},
                    {'title': 'Wikipédia', 'url': 'https://fr.wikipedia.org/wiki/LGV'}]}, 'w'))
    shell.full.navigate(1)
    app.processEvents()
    page = shell.full.cards_page
    chips = page.findChildren(QPushButton, 'chip')
    assert [chip.text() for chip in chips] == ['1. www.sncf-connect.com ↗', '2. fr.wikipedia.org ↗']
    assert chips[0].geometry().top() == chips[1].geometry().top()  # one line when there is room
    copy = page.findChild(QPushButton, 'copyCard')
    copy.click()
    copied = QGuiApplication.clipboard().text()
    assert 'Environ deux heures.' in copied and 'https://fr.wikipedia.org/wiki/LGV' in copied
    assert copy.text() == 'Copié ✓'
    copy.restore.timeout.emit()
    assert copy.text() == 'Copier'


def test_sidebar_counts_unseen_cards_and_marks_running_activity(shell, app):
    from jarvis.desktop.presentation import project_activity, project_task
    c, window = shell.controller, shell.full
    cards, activity = window.nav[1], window.nav[2]
    shell.show_full()
    listen(c)
    assert cards.badge == 0 and not activity.live
    c.voice_event(project_activity('get_volume', {'ok': True, 'volume': 40}, 'v'))
    c.voice_event(project_activity('list_calendar_events', {'ok': True, 'events': [{'title': 'Point', 'start': '10:00'}]}, 'cal'))
    assert cards.badge == 2 and '2 nouvelles' in cards.accessibleName()
    window.navigate(1)
    assert cards.badge == 0
    c.voice_event(project_activity('list_reminders', {'ok': True, 'reminders': [{'text': 'Pain'}]}, 'r'))
    assert cards.badge == 0  # arrives under the user's eyes
    window.navigate(0)
    c.clear_cards()
    assert cards.badge == 0
    c.voice_event(project_task({'id': 'm', 'objective': 'Trier', 'status': 'running', 'current_tool': 'list_files', 'steps': []}))
    assert activity.live and not activity.timer.isActive()  # reduced motion: steady dot
    c.reduced_motion = False
    c.changed.emit()
    assert activity.timer.isActive()
    c.voice_event(project_task({'id': 'm', 'objective': 'Trier', 'status': 'completed', 'steps': []}))
    assert not activity.live and not activity.timer.isActive()


def test_status_title_takes_the_state_colour_and_fades_unless_motion_is_reduced(shell, app):
    from PySide6.QtCore import QPropertyAnimation
    from jarvis.desktop.visuals import STATE_COLORS, state_tint
    assert state_tint('off') == '#eef7ff' and state_tint('inconnu') == '#eef7ff'
    assert state_tint('thinking') not in {'#eef7ff', STATE_COLORS['thinking']}
    assert state_tint('error', amount=1.0) == STATE_COLORS['error']
    c, panel = shell.controller, shell.full.assistant
    shell.show_full()
    assert '#eef7ff' in panel.status.styleSheet()
    listen(c, 'thinking')
    assert state_tint('thinking') in panel.status.styleSheet()
    assert panel.status_fade.state() != QPropertyAnimation.State.Running and panel.status_opacity.opacity() == 1.0
    c.reduced_motion = False
    c.voice_event({'type': 'state', 'state': 'speaking', 'mic_open': True})
    assert state_tint('speaking') in panel.status.styleSheet()
    assert panel.status_fade.state() == QPropertyAnimation.State.Running
    c.reduced_motion = True
    c.changed.emit()
    assert panel.status_fade.state() != QPropertyAnimation.State.Running and panel.status_opacity.opacity() == 1.0
