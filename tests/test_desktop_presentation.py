from jarvis.desktop.presentation import project_activity, project_card, project_task, safe_url


def test_cards_project_only_supported_fields_and_preserve_source_identity():
    result = {'ok': True, 'message': '<b>Résumé</b>', 'external_knowledge_retrieved': True,
              'token': 'PRIVATE_TOKEN', 'arguments': 'PRIVATE_ARGS',
              'sources': [{'title': 'Article', 'url': 'https://example.com/read?id=42#part'},
                          {'title': 'Secret', 'url': 'https://example.com/?token=PRIVATE_TOKEN'},
                          {'title': 'Local', 'url': 'file:///PRIVATE_FILE'}]}
    card = project_card('web_answer', result)
    assert card['body'] == '<b>Résumé</b>'  # The widget must render this as plain text.
    assert card['sources'] == [{'title': 'Article', 'url': 'https://example.com/read?id=42'}]
    assert 'PRIVATE' not in str(card)
    assert project_card('unknown', result) is None
    assert project_card('web_answer', {**result, 'external_knowledge_retrieved': False}) is None
    assert project_card('web_answer', {**result, 'ok': False}) is None
    assert project_card('web_answer', {**result, 'requires_confirmation': True}) is None
    assert safe_url('javascript:alert(1)') is None
    assert safe_url('https://user:PRIVATE@example.com') is None


def test_agenda_and_reminders_are_bounded_and_never_copy_raw_payloads():
    agenda = project_card('list_calendar_events', {'ok': True,
        'events': [{'title': 'Réunion', 'start': '2026-10-18T10:00', 'notes': 'PRIVATE_NOTE'}] * 50})
    assert len(agenda['items']) == 6 and 'Réunion' in agenda['items'][0]
    assert 'PRIVATE' not in str(agenda)
    reminder = project_card('list_reminders', {'ok': True,
        'reminders': [{'text': 'Appeler', 'due_at': 0, 'token': 'PRIVATE_TOKEN'}]})
    assert 'Appeler' in reminder['items'][0]
    assert 'PRIVATE' not in str(reminder)
    assert project_card('list_calendar_events', {'ok': True, 'events': []})['items'] == []


def test_states_distinguish_preparation_from_verified_effects_and_unknown_outputs():
    assert project_activity('open_app', None, '1', 'started')['status'] == 'running'
    assert project_activity('open_app', {'ok': True}, '1')['status'] == 'received'
    assert project_activity('open_app', {'ok': True, 'state_confirmed': True}, '1')['status'] == 'verified'
    assert project_activity('open_app', {'ok': False, 'requires_confirmation': True}, '1')['status'] == 'confirmation'
    assert project_activity('run_task', {'ok': True, 'task_started': True}, '1')['status'] == 'received'
    search = project_activity('search_the_web', {'ok': True, 'search_started': True}, '1')
    assert search['id'] == 'background:web' and search['status'] == 'running'
    done = project_activity('search_the_web', {'ok': True, 'external_knowledge_retrieved': True,
        'message': 'Réponse', 'sources': []}, 'other-id')
    assert done['id'] == search['id'] and done['card']['body'] == 'Réponse'


def test_task_projection_drops_pending_tokens_summaries_goals_and_error_details():
    task = project_task({'id': 'a', 'status': 'needs_confirmation', 'goal': 'PRIVATE_GOAL',
        'pending': {'token': 'PRIVATE_TOKEN'}, 'summary': 'PRIVATE_SUMMARY',
        'steps': [{'tool': 'open_app', 'ok': True, 'state_confirmed': False, 'error_code': 'PRIVATE_ERROR'}]})
    assert task['status'] == 'needs_confirmation'
    assert task['steps'] == [{'label': 'Application', 'status': 'received'}]
    assert 'PRIVATE' not in str(task)


def test_screen_card_contains_only_bounded_analysis_and_capture_scope():
    result = {'ok': True, 'analysis': '<b>Lecture</b>' + 'a' * 2000, 'source': 'screen',
              'image_path': '/PRIVATE_FILE.png', 'model': 'PRIVATE_MODEL', 'token': 'PRIVATE_TOKEN',
              'target_app': 'PRIVATE_APP', 'question': 'PRIVATE_QUESTION'}
    card = project_card('ask_about_screen', result)
    assert card['kind'] == 'screen' and len(card['body']) == 1600
    assert card['body'].startswith('<b>Lecture</b>')
    assert card['sources'] == [] and 'Écran entier' in card['items'][0]
    assert 'PRIVATE' not in str(card)
    assert project_card('describe_screen', {**result, 'ok': False}) is None
    assert project_card('ask_about_screen', {'ok': True, 'message': 'PRIVATE_FALLBACK'}) is None
    assert project_card('capture_screen', {'ok': True, 'state_confirmed': True})['title'] == 'Capture effectuée'
    assert project_card('capture_screen', {'ok': True}) is None


def test_mission_projection_accepts_only_explicit_objective_and_known_tool_labels():
    task = project_task({'id': 'a', 'status': 'running', 'objective': 'x' * 500,
                         'current_tool': 'open_app', 'steps': [],
                         'goal': 'PRIVATE_GOAL', 'summary': 'PRIVATE_SUMMARY', 'pending': {'token': 'PRIVATE'}})
    assert len(task['objective']) == 300 and task['current'] == 'Application'
    assert 'PRIVATE' not in str(task)



def test_productivity_cards_bound_items_and_drop_unprojected_payloads():
    payload = {'ok': True, 'token': 'PRIVATE_TOKEN', 'path': '/PRIVATE_PATH',
               'items': [{'text': 'Préparer', 'done': True, 'evidence': 'PRIVATE_QUOTE'}] * 20}
    for tool, kind in [('manage_checklist', 'checklist'), ('extract_document_actions', 'document')]:
        card = project_card(tool, payload)
        assert card['kind'] == kind and len(card['items']) == 6
        assert 'PRIVATE' not in str(card)
    timer = project_card('list_timers', {'ok': True, 'timers': [
        {'label': 'Thé', 'state': 'running', 'deadline': 'PRIVATE_DEADLINE'}] * 20})
    assert len(timer['items']) == 6 and 'PRIVATE' not in str(timer)
    assert 'moment' in timer['body']
    for state in ['paused', 'waiting_dependency', 'blocked']:
        assert project_task({'id': 'a', 'status': state, 'steps': []})['status'] == state
