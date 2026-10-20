"""Bounded, explicit projections of tool results for the desktop (no raw payloads)."""
from datetime import datetime
import json
from urllib.parse import parse_qsl, urlsplit, urlunsplit

LABELS = {
    'start_timer': 'Minuteur', 'list_timers': 'Minuteurs', 'cancel_timer': 'Minuteur', 'timer_finished': 'Minuteur termine',
    'search_notes': 'Recherche de notes', 'read_note': 'Lecture de note', 'append_note': 'Ajout a une note',
    'manage_checklist': 'Checklist', 'find_free_slots': 'Disponibilites', 'calendar_conflicts': 'Conflits d’agenda',
    'compare_documents': 'Comparaison de documents', 'extract_document_actions': 'Extraction du document',
    'pause_task': 'Pause de mission', 'resume_task': 'Reprise de mission',
    'open_app': 'Application', 'close_app': 'Application', 'focus_window': 'Fenêtre',
    'open_file': 'Fichier', 'open_folder': 'Dossier', 'list_files': 'Fichiers',
    'find_files': 'Recherche de fichiers', 'move_file': 'Déplacement', 'rename_file': 'Renommage',
    'search_the_web': 'Recherche web', 'web_answer': 'Recherche web', 'summarize_url': 'Page web',
    'set_reminder': 'Rappel', 'list_reminders': 'Rappels', 'cancel_reminder': 'Rappel',
    'list_calendar_events': 'Agenda', 'create_calendar_event': 'Agenda',
    'list_unread_emails': 'Mails', 'summarize_unread_emails': 'Résumé des mails',
    'schedule_message': 'Message planifié', 'prepare_send_message': 'Message',
    'confirm_action': 'Confirmation', 'cancel_action': 'Annulation',
    'run_task': 'Tâche', 'task_status': 'Tâche', 'cancel_task': 'Tâche',
    'remember_context': 'Mémoire', 'recall': 'Mémoire', 'recent_activity': 'Activité', 'recent_missions': 'Missions', 'capture_screen': 'Capture d’écran', 'ask_about_screen': 'Analyse d’écran',
    'describe_screen': 'Analyse d’écran', 'capture_window': 'Capture de fenêtre', 'capture_region': 'Capture de zone',
    'get_volume': 'Volume', 'set_volume': 'Volume', 'browse_open_url': 'Navigateur',
    'enable_safe_mode': 'Mode sécurité', 'disable_safe_mode': 'Mode sécurité',
}
STATUS_TEXT = {
    'running': 'En cours', 'received': 'Résultat reçu', 'verified': 'État vérifié',
    'confirmation': 'Accord vocal attendu', 'error': 'L’outil signale un problème',
    'cancelled': 'Annulée', 'unknown': 'Résultat indisponible',
}
TASK_TEXT = {
    'queued': 'En attente de ressources',
    'paused': 'Mission en pause', 'waiting_dependency': 'Attend la mission precedente', 'blocked': 'Suite non lancee',
    'running': 'Tâche en cours', 'cancelling': 'Annulation demandée',
    'completed': 'Tâche terminée', 'cancelled': 'Tâche annulée',
    'needs_confirmation': 'Action préparée · accord vocal requis', 'needs_clarification': 'Précision vocale attendue',
    'failed': 'Tâche en échec', 'budget_exceeded': 'Limite de la tâche atteinte',
    'unknown': 'Résultat indisponible',
}
SCREEN_TOOLS = frozenset({'describe_screen', 'ask_about_screen', 'capture_screen', 'capture_window', 'capture_region'})
MISSION_GUIDANCE = {
    'paused': 'Mission en attente mise en pause. Demandez vocalement sa reprise pour la remettre en file.',
    'waiting_dependency': 'Attend la fin de la mission precedente, sans reserver le bureau.',
    'blocked': 'La mission precedente n’a pas termine avec le statut completed. Cette suite n’a execute aucune action.',
    'queued': 'Cette mission attend une place ou la libération du bureau. Aucune action n’a encore été lancée.',
    'running': 'Jarvis traite votre objectif. Les étapes apparaissent après leur exécution.',
    'cancelling': 'Annulation demandée. L’action déjà lancée peut encore se terminer.',
    'completed': 'Le planificateur a terminé. Consultez les états des étapes pour vérifier les effets confirmés.',
    'needs_confirmation': 'Le planificateur a préparé une action. Sa confirmation vocale et son résultat se suivent dans Activité.',
    'needs_clarification': 'Répondez vocalement à la question de Jarvis pour préciser la suite.',
    'failed': 'La mission n’a pas abouti. Certaines étapes peuvent néanmoins avoir été exécutées.',
    'budget_exceeded': 'La limite d’exécution est atteinte. Vérifiez les étapes avant une nouvelle demande.',
    'cancelled': 'La mission est arrêtée. Les actions déjà effectuées ne sont pas annulées.',
    'unknown': 'Résultat final indisponible. Vérifiez les effets avant de redemander cette mission.',
}


def plain(value, limit=180):
    if not isinstance(value, str):
        return ''
    return ''.join(c for c in value if c in '\n\t' or ord(c) >= 32)[:limit].strip()


def result_dict(raw):
    if hasattr(raw, 'to_livekit_dict'):
        raw = raw.to_livekit_dict()
    if isinstance(raw, str) and len(raw) <= 131072:
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError, RecursionError):
            return {}
    return raw if isinstance(raw, dict) else {}


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme not in {'https', 'http'} or not parts.hostname or parts.username or parts.password:
            return None
        sensitive = {'key', 'api_key', 'token', 'access_token', 'auth', 'authorization',
                     'signature', 'x-amz-signature', 'x-goog-signature', 'credential', 'secret'}
        if any(key.lower() in sensitive for key, _ in parse_qsl(parts.query)):
            return None
        # Preserve article-identifying query parameters; never carry credentials.
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))
    except ValueError:
        return None


def date_text(value):
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value).astimezone().strftime('%d/%m · %H:%M')
        except (ValueError, OSError, OverflowError):
            return ''
    value = plain(value, 70)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime('%d/%m · %H:%M')
    except ValueError:
        return value


def project_card(name, result):
    if result.get('ok') is not True or result.get('requires_confirmation'):
        return None
    kind, title, body, items, sources = '', '', '', [], []
    if name in {'start_timer', 'cancel_timer', 'timer_finished', 'list_timers'}:
        kind, title = 'timers', 'Vos minuteurs'
        states = {'running': 'En cours', 'completed': 'Termine', 'cancelled': 'Annule'}
        rows = result.get('timers', []) if name == 'list_timers' else [result]
        for timer in rows[:6] if isinstance(rows, list) else []:
            if isinstance(timer, dict):
                items.append(plain(timer.get('label'), 100) + ' · ' + states.get(timer.get('state'), 'Etat inconnu'))
        body = 'Etat au moment du resultat. Les minuteurs cessent a la fermeture de Jarvis.'
    elif name == 'manage_checklist' and isinstance(result.get('items'), list):
        kind, title = 'checklist', plain(result.get('title'), 100) or 'Votre checklist'
        for item in result['items'][:6]:
            if isinstance(item, dict):
                items.append(('✓ ' if item.get('done') else '○ ') + plain(item.get('text'), 180))
        body = f"{len(result['items'])} element(s) · {len(items)} affiche(s)"
    elif name in {'find_free_slots', 'calendar_conflicts'}:
        kind, title = 'calendar', 'Plages disponibles' if name == 'find_free_slots' else 'Chevauchements d’agenda'
        rows = result.get('slots', []) if name == 'find_free_slots' else result.get('conflicts', [])
        for row in rows[:6] if isinstance(rows, list) else []:
            if isinstance(row, dict):
                items.append(date_text(row.get('start')) + ' → ' + date_text(row.get('end')))
        body = plain(result.get('message'), 300)
    elif name in {'compare_documents', 'extract_document_actions'} and isinstance(result.get('items'), list):
        kind, title = 'document', 'Analyse d’extraits à vérifier'
        body = 'Proposition générée à vérifier. Citations dans le résultat vocal. Aucune action lancée.'
        if result.get('truncated'):
            body += ' Document tronqué : analyse partielle.'
        for row in result['items'][:6]:
            if isinstance(row, dict):
                items.append(plain(row.get('text'), 180))
    elif name == 'summarize_unread_emails' and isinstance(result.get('items'), list):
        kind, title = 'mail', 'Mails non lus (résumé)'
        body = 'Résumé généré à vérifier. Aucun mail envoyé ni modifié ; non-lus conservés.'
        for row in result['items'][:6]:
            if isinstance(row, dict):
                head = plain(row.get('subject'), 80) or plain(row.get('sender'), 80)
                summary = plain(row.get('summary'), 180)
                items.append(' · '.join(v for v in (head, summary) if v))
    elif name in {'describe_screen', 'ask_about_screen'}:
        analysis = plain(result.get('analysis'), 1600)
        if not analysis:
            return None
        kind, title, body = 'screen', 'Analyse de l’écran', analysis
        items = ['Observation ponctuelle · ' + ('Écran entier' if result.get('source') == 'screen' else 'Fenêtre')]
    elif name in SCREEN_TOOLS and result.get('state_confirmed') is True:
        kind, title, body = 'screen', 'Capture effectuée', 'Capture ponctuelle confirmée. Aucune analyse visuelle n’est déduite de cette capture seule.'
    elif name == 'list_calendar_events' and isinstance(result.get('events'), list):
        kind, title = 'calendar', 'Votre agenda'
        for row in result['events'][:6]:
            if isinstance(row, dict):
                items.append(' · '.join(v for v in (date_text(row.get('start')), plain(row.get('title'))) if v))
        body = 'Aucun rendez-vous dans ce résultat.' if not items else f"{len(result['events'])} rendez-vous · {len(items)} affiché(s)"
    elif name == 'list_reminders' and isinstance(result.get('reminders'), list):
        kind, title = 'reminders', 'Vos rappels'
        for row in result['reminders'][:6]:
            if isinstance(row, dict):
                items.append(' · '.join(v for v in (date_text(row.get('due_at')), plain(row.get('text'))) if v))
        body = 'Aucun rappel en attente.' if not items else f"{len(result['reminders'])} rappel(s) · {len(items)} affiché(s)"
    elif name in {'web_answer', 'search_the_web', 'summarize_url'}:
        if result.get('search_started'):
            return None
        if name != 'summarize_url' and result.get('external_knowledge_retrieved') is not True:
            return None
        kind, title, body = 'web', 'Réponse web' if name != 'summarize_url' else 'Résumé de la page', plain(result.get('message'), 1600)
        raw_sources = result.get('sources') if isinstance(result.get('sources'), list) else []
        if name == 'summarize_url':
            raw_sources = [{'url': result.get('url'), 'title': 'Page consultée'}]
        for source in raw_sources[:4]:
            if isinstance(source, dict) and (url := safe_url(source.get('url'))):
                sources.append({'url': url, 'title': plain(source.get('title'), 100) or urlsplit(url).hostname})
    elif name in {'get_volume', 'set_volume'}:
        volume = result.get('volume')
        if isinstance(volume, (int, float)) and not isinstance(volume, bool) and 0 <= volume <= 100:
            kind, title, body = 'system', 'Volume du Mac', f'{volume:g} %'
    elif name in {'token_usage', 'token_usage_by_model', 'token_usage_by_project',
                  'token_usage_trend', 'compare_token_usage'}:
        kind, title = 'usage', 'Consommation de tokens'
        body = plain(result.get('message'), 400)
        for row in (result.get('models') or result.get('projects') or [])[:6]:
            if isinstance(row, dict):
                label = plain(row.get('model') or row.get('project'), 80)
                total = row.get('total_tokens')
                suffix = f' · {total / 1e6:.0f} M' if isinstance(total, (int, float)) else ''
                items.append(label + suffix)
    elif name in {'system_snapshot', 'system_usage_history'}:
        kind, title, body = 'system', 'Activité machine', plain(result.get('message'), 400)
    elif name == 'top_processes' and isinstance(result.get('processes'), list):
        kind, title = 'system', 'Processus gourmands'
        unit = '% CPU' if result.get('by') == 'cpu' else '% mémoire'
        for row in result['processes'][:6]:
            if isinstance(row, dict):
                items.append(plain(row.get('name'), 60) + f" · {row.get('value')} {unit}")
        body = plain(result.get('message'), 200)
    if not kind:
        return None
    return {'kind': kind, 'title': title, 'body': body, 'items': items, 'sources': sources}


def project_activity(name, raw, activity_id, phase='result'):
    result = result_dict(raw)
    if phase == 'started':
        status = 'running'
    elif phase == 'cancelled':
        status = 'cancelled'
    elif phase == 'error' or result.get('ok') is False:
        status = 'error'
    else:
        status = 'received'
    if result.get('requires_confirmation') is True:
        status = 'confirmation'
    elif result.get('search_started') is True:
        status = 'running'
    elif result.get('ok') is True and result.get('state_confirmed') is True:
        status = 'verified'
    if name == 'search_the_web':
        activity_id = 'background:web'
    return {'type': 'activity', 'id': activity_id, 'label': LABELS.get(name, 'Outil Jarvis'),
            'screen': name in SCREEN_TOOLS,
            'status': status, 'card': project_card(name, result) if phase == 'result' else None}


def project_task(snapshot):
    if not isinstance(snapshot, dict) or not snapshot.get('id'):
        return None
    steps = []
    raw_steps = snapshot.get('steps', [])
    for step in raw_steps[:25] if isinstance(raw_steps, list) else []:
        if isinstance(step, dict):
            status = 'error' if step.get('ok') is not True else (
                'verified' if step.get('state_confirmed') is True else 'received')
            steps.append({'label': LABELS.get(step.get('tool'), 'Outil Jarvis'), 'status': status})
    status = snapshot.get('status')
    return {'type': 'task_progress', 'id': plain(snapshot['id'], 80),
            'objective': plain(snapshot.get('objective'), 300),
            'read_only': snapshot.get('read_only') is True,
            'current': LABELS.get(snapshot.get('current_tool'), 'Outil Jarvis') if snapshot.get('current_tool') else '',
            'status': status if status in TASK_TEXT else 'unknown', 'steps': steps,
            'step_count': len(raw_steps) if isinstance(raw_steps, list) else 0}

