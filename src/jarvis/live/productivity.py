"""Voice adapters for explicit, bounded daily-work capabilities."""
import asyncio
from livekit.agents import function_tool
from jarvis.capabilities.checklists import ChecklistsCapability
from jarvis.capabilities.calendar_planning import CalendarPlanning
from jarvis.capabilities.timers import TimerService


def checklist_store(registry):
    if not hasattr(registry, 'checklists'):
        registry.checklists = ChecklistsCapability()
    return registry.checklists


def timer_service(registry):
    if not hasattr(registry, 'timers'):
        if not hasattr(registry, 'task_announcement_lock'):
            registry.task_announcement_lock = asyncio.Lock()
        async def finished(timer):
            registry._activity({'phase': 'result', 'tool': 'timer_finished', 'id': 'timer:'+timer['id'], 'result': {'ok': True, **timer}})
            if getattr(registry, 'task_notifier', None) is not None:
                async with registry.task_announcement_lock:
                    if registry.task_notifier is not None:
                        await registry.task_notifier('Annonce brievement : le minuteur « '+timer['label']+' » est termine. Ne lance aucune action supplementaire.')
        registry.timers = TimerService(finished)
    return registry.timers


def productivity_tools(r):
    @function_tool(name='start_timer', description='Lance un minuteur vocal pour cette session : seconds entre 1 et 86400, label court. Plusieurs minuteurs possibles. Fermer Jarvis les annule ; ce ne sont pas des rappels persistants.')
    @r._journaled('start_timer')
    async def start_timer(seconds: int, label: str = 'Minuteur') -> dict:
        return timer_service(r).start(seconds, label).to_livekit_dict()

    @function_tool(name='list_timers', description='Liste les minuteurs de cette session avec leur id, etat et temps restant mesure au moment de la demande.')
    async def list_timers() -> dict:
        return timer_service(r).status().to_livekit_dict()

    @function_tool(name='cancel_timer', description='Annule uniquement le minuteur dont timer_id vient de list_timers ou start_timer. Ne devine pas lequel si plusieurs noms correspondent.')
    @r._journaled('cancel_timer')
    async def cancel_timer(timer_id: str) -> dict:
        return timer_service(r).cancel(timer_id).to_livekit_dict()

    @function_tool(name='search_notes', description='Recherche un mot ou une expression dans les 200 notes Jarvis les plus recentes. Retourne des note_id exacts, sans creer de note. Recherche limitee aux extraits lisibles.')
    @r._journaled('search_notes')
    async def search_notes(query: str) -> dict:
        return (await asyncio.to_thread(r.notes.search_notes, query)).to_livekit_dict()

    @function_tool(name='read_note', description='Relit une note Jarvis avec son note_id exact obtenu par search_notes ou list_notes (le champ name). Lecture bornee ; une note tronquee est signalee.')
    @r._journaled('read_note')
    async def read_note(note_id: str) -> dict:
        return (await asyncio.to_thread(r.notes.read_note, note_id)).to_livekit_dict()

    @function_tool(name='append_note', description='Sur demande explicite, ajoute text a la fin d’une note Jarvis existante sans remplacer son contenu. note_id doit etre exact ; demande laquelle si la recherche est ambigue. Ne cree pas de note en cas d’erreur.')
    @r._journaled('append_note')
    async def append_note(note_id: str, text: str) -> dict:
        return (await asyncio.to_thread(r.notes.append_note, note_id, text)).to_livekit_dict()

    @function_tool(name='manage_checklist', description='Gere les checklists locales persistantes sur demande : operation create (text=titre), list, show (list_id), add (list_id,text), check (list_id,item_id,done). IDs exacts issus des lectures. Aucun effacement ni envoi ; ne coche pas sans demande explicite.')
    @r._journaled('manage_checklist')
    async def manage_checklist(operation: str, list_id: int | None = None, text: str | None = None, item_id: int | None = None, done: bool = True) -> dict:
        return (await asyncio.to_thread(checklist_store(r).manage, operation, list_id, text, item_id, done)).to_livekit_dict()

    @function_tool(name='find_free_slots', description='Cherche les plages libres d’au moins duration_minutes dans l’agenda Apple entre start et end ISO AVEC fuseau explicite, sept jours maximum. Lecture native requise. Ne reserve rien ; une permission ou date illisible est une erreur, jamais du temps libre.')
    @r._journaled('find_free_slots')
    async def find_free_slots(start: str, end: str, duration_minutes: int = 30) -> dict:
        return (await asyncio.to_thread(CalendarPlanning(r.calendar).analyze, 'free', start, end, duration_minutes)).to_livekit_dict()

    @function_tool(name='calendar_conflicts', description='Liste les chevauchements de rendez-vous entre start et end ISO avec fuseau explicite, sept jours maximum. Lecture seule de l’agenda natif, ne deplace ni ne supprime aucun evenement.')
    @r._journaled('calendar_conflicts')
    async def calendar_conflicts(start: str, end: str) -> dict:
        return (await asyncio.to_thread(CalendarPlanning(r.calendar).analyze, 'conflicts', start, end)).to_livekit_dict()

    @function_tool(name='compare_documents', description='Compare les extraits de deux documents locaux aux chemins exacts left et right obtenus par recherche de fichiers. Lecture seule ; analyse generee avec citations exactes a verifier. Ne deduis pas une absence dans le document entier depuis un extrait tronque.')
    @r._journaled('compare_documents')
    async def compare_documents(left: str, right: str) -> dict:
        return (await asyncio.to_thread(r.document.compare, left, right)).to_livekit_dict()

    @function_tool(name='extract_document_actions', description='Extrait actions, decisions et dates explicites d’un document local path exact. Propose une liste avec preuves citees, sans creer de rappel ni executer une action. Restitue les inconnues sans inventer responsable ou echeance.')
    @r._journaled('extract_document_actions')
    async def extract_document_actions(path: str) -> dict:
        return (await asyncio.to_thread(r.document.extract_actions, path)).to_livekit_dict()

    @function_tool(name='pause_task', description='Met en pause uniquement une mission EN ATTENTE, avec task_id exact de task_status. N’interrompt jamais une mission qui a deja commence. Pour arreter une mission en cours, demander cancel_task selon le choix de l’utilisateur.')
    @r._journaled('pause_task')
    async def pause_task(task_id: str) -> dict:
        return r.tasks.pause(task_id)

    @function_tool(name='resume_task', description='Remet en file une mission en pause par task_id exact. Elle conserve ses dependances et attend encore sa place ; aucune action terminee n’est rejouee.')
    @r._journaled('resume_task')
    async def resume_task(task_id: str) -> dict:
        return r.tasks.resume(task_id)

    return [start_timer, list_timers, cancel_timer, search_notes, read_note, append_note,
            manage_checklist, find_free_slots, calendar_conflicts, compare_documents,
            extract_document_actions, pause_task, resume_task]
