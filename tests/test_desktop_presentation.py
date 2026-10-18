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
