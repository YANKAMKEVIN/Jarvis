"""Ten daily-work capabilities, exercised without microphone/network/native UI."""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import pytest

from jarvis.capabilities.calendar_planning import CalendarPlanning
from jarvis.capabilities.checklists import ChecklistsCapability
from jarvis.capabilities.document import DocumentCapability
from jarvis.capabilities.notes import NotesCapability
from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.timers import TimerService
from jarvis.live.registry import ToolRegistry
from jarvis.planner import ModelTurn, PlannerEngine, ScriptedModel
from jarvis.planner.engine import TaskOutcome
from jarvis.planner.tasks import TaskManager


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(wait(), 3)


def test_notes_save_collision_search_read_and_non_destructive_append(tmp_path):
    cap = NotesCapability(tmp_path, clock=lambda: datetime(2026, 10, 19))
    first = cap.save_note('Premier contenu', 'Réunion')
    second = cap.save_note('Deuxième contenu', 'Réunion')
    assert first.data['path'] != second.data['path']
    identifier = Path(first.data['path']).name
    assert cap.search_notes('PREMIER').data['notes'][0]['note_id'] == identifier
    before = Path(first.data['path']).read_bytes()
    assert cap.append_note(identifier, 'Une nouvelle idée').ok
    assert Path(first.data['path']).read_bytes().startswith(before)
    assert 'nouvelle idée' in cap.read_note(identifier).data['text']
    assert len(cap.search_notes('contenu').data['notes']) == 2
    (tmp_path/'empty.md').touch()
    assert cap.search_notes('empty').data['notes'][0]['note_id'] == 'empty.md'


def test_notes_refuse_paths_symlinks_and_invalid_titles(tmp_path):
    cap = NotesCapability(tmp_path/'notes')
    cap.notes_dir.mkdir()
    outside = tmp_path/'private.md'
    outside.write_text('PRIVATE')
    (cap.notes_dir/'link.md').symlink_to(outside)
    for value in ['../private.md', str(outside), 'link.md', 'missing.md']:
        assert not cap.read_note(value).ok
        assert not cap.append_note(value, 'overwrite').ok
    assert outside.read_text() == 'PRIVATE'
    assert not cap.save_note('text', 'title\n# injection').ok
    assert not cap.search_notes('').ok


def test_checklists_persist_and_ids_never_modify_another_list(tmp_path):
    path = tmp_path/'checklists.db'
    cap = ChecklistsCapability(path)
    one = cap.manage('create', text='Courses').data['list_id']
    two = cap.manage('create', text='Voyage').data['list_id']
    item = cap.manage('add', one, 'Lait').data['items'][0]['id']
    assert not cap.manage('check', two, item_id=item).ok
    assert cap.manage('check', one, item_id=item).data['items'][0]['done'] == 1
    new = ChecklistsCapability(path)
    assert new.manage('show', one).data['items'][0]['text'] == 'Lait'
    assert new.manage('check', one, item_id=item, done=False).data['items'][0]['done'] == 0
    assert len(new.manage('list').data['lists']) == 2
    assert new.clear() == 2 and new.manage('list').data['lists'] == []
    assert not cap.manage('check', one, item_id=True).ok


def test_checklist_concurrent_adds_preserve_every_item(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    cap = ChecklistsCapability(tmp_path/'lists.db')
    key = cap.manage('create', text='Concurrent').data['list_id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: cap.manage('add', key, str(i)), range(12)))
    assert all(r.ok for r in results)
    assert len(cap.manage('show', key).data['items']) == 12
    for i in range(87):
        assert cap.manage('add', key, f'fill-{i}').ok
    with ThreadPoolExecutor(max_workers=4) as pool:
        final = list(pool.map(lambda i: cap.manage('add', key, f'last-{i}'), range(8)))
    assert sum(r.ok for r in final) == 1
    assert len(cap.manage('show', key).data['items']) == 100


def test_timers_expire_by_monotonic_deadline_and_cancel_independently():
    async def scenario():
        time = [10.0]
        wake = asyncio.Event()
        announced = []
        async def sleep(seconds): await wake.wait()
        async def notify(timer): announced.append(timer)
        service = TimerService(notify, clock=lambda: time[0], sleep=sleep)
        first = service.start(20, 'Thé').data['id']
        second = service.start(40, 'Lecture').data['id']
        assert service.cancel(second).data['state'] == 'cancelled'
        time[0] = 31
        wake.set()
        await until(lambda: bool(announced))
        assert announced[0]['id'] == first
        assert [t['state'] for t in service.status().data['timers']] == ['completed', 'cancelled']
        assert not service.start(float('nan')).ok and not service.start(True).ok
        assert not service.cancel('unknown').ok
        await service.aclose()
        assert not service.start(1).ok
    asyncio.run(scenario())


def test_closing_timer_service_prevents_late_announcement():
    async def scenario():
        calls = []
        async def notify(timer): calls.append(timer)
        service = TimerService(notify)
        for i in range(10): assert service.start(3600, str(i)).ok
        assert not service.start(3600).ok
        await service.aclose()
        assert not calls and all(t['state'] == 'cancelled' for t in service.status().data['timers'])
    asyncio.run(scenario())


def calendar(events):
    return CalendarPlanning(SimpleNamespace(read_interval=lambda *args: ToolResult.success('read', 'ok', events=events)))


def test_free_slots_merge_overlaps_and_account_for_overnight_events():
    cap = calendar([
        {'title': 'Nuit', 'start': '2026-10-18T23:00+02:00', 'end': '2026-10-19T10:00+02:00'},
        {'title': 'Point', 'start': '2026-10-19T09:30+02:00', 'end': '2026-10-19T10:30+02:00'},
        {'title': 'Midi', 'start': '2026-10-19T12:00+02:00', 'end': '2026-10-19T13:00+02:00'}])
    free = cap.analyze('free', '2026-10-19T09:00+02:00', '2026-10-19T14:00+02:00', 60)
    assert free.ok and [s['start'] for s in free.data['slots']] == ['2026-10-19T10:30+02:00', '2026-10-19T13:00+02:00']
    conflicts = cap.analyze('conflicts', '2026-10-19T09:00+02:00', '2026-10-19T14:00+02:00')
    assert len(conflicts.data['conflicts']) == 1
    assert conflicts.data['conflicts'][0]['start'] == '2026-10-19T09:30+02:00'


def test_calendar_unreadable_times_or_missing_permission_are_never_free_time():
    cap = calendar([{'start': 'lundi matin', 'end': 'lundi soir'}])
    assert cap.analyze('free', '2026-10-19T09:00+02:00', '2026-10-19T18:00+02:00').error_code == 'incomplete_calendar'
    assert not calendar([]).analyze('free', '2026-10-19T09:00', '2026-10-19T18:00').ok
    denied = CalendarPlanning(SimpleNamespace(read_interval=lambda *a: ToolResult.failure('read', 'Refus', 'denied')))
    assert denied.analyze('free', '2026-10-19T09:00Z', '2026-10-19T18:00Z').error_code == 'denied'
    busy = calendar([{'start': '2026-10-19T00:00Z', 'end': '2026-10-20T00:00Z'}])
    assert busy.analyze('free', '2026-10-19T09:00Z', '2026-10-19T18:00Z').data['slots'] == []


def test_eventkit_interval_uses_requested_bounds_not_today():
    from jarvis.tools.eventkit_calendar import EventKitCalendarReader
    bounds = []
    class Backend:
        def authorization_status(self): return 3
        def events_between(self, start, end):
            bounds.append((start, end))
            return []
    reader = EventKitCalendarReader(Backend())
    assert reader.read_interval(1000, 5000)['events'] == []
    assert bounds == [(1000, 5000)]


def document(rows, texts=None):
    texts = texts or {'left': 'Le lancement est prévu le 12 juin. Envoyer le dossier.', 'right': 'Le lancement est prévu le 15 juin.'}
    class Files:
        def read_text(self, path, max_chars=12000):
            return {'name': path, 'text': texts[path], 'truncated': True}
    class Model:
        def complete(self, messages, tools):
            assert tools == [] and 'donnees' in messages[0]['content']
            return SimpleNamespace(text=json.dumps(rows))
    return DocumentCapability(Files(), Model())


def test_document_comparison_and_actions_keep_grounded_quotes_and_partial_flag():
    result = document([{'type': 'difference', 'text': 'La date change.', 'evidence_left': '12 juin', 'evidence_right': '15 juin'}]).compare('left', 'right')
    assert result.ok and result.data['truncated']
    assert result.data['items'][0]['evidence_left'] == '12 juin'
    result = document([{'type': 'action', 'text': 'Envoyer le dossier', 'evidence': 'Envoyer le dossier.'}]).extract_actions('left')
    assert result.ok and result.data['items'][0]['type'] == 'action'
    assert result.data['generated_analysis']


@pytest.mark.parametrize('row', [
    {'type': 'action', 'text': 'Téléphoner', 'evidence': 'Texte absent'},
    {'type': 'secret', 'text': 'Envoyer', 'evidence': 'Envoyer le dossier.'},
    {'type': 'date', 'text': 'Date', 'evidence': ''}])
def test_document_extract_refuses_ungrounded_or_invalid_items(row):
    assert not document([row]).extract_actions('left').ok


def test_mission_dependency_runs_only_after_completed_and_does_not_reserve_desktop():
    async def scenario():
        entered, release = [], asyncio.Event()
        class Engine:
            async def run(self, goal, cancel, on_step):
                entered.append(goal)
                if goal == 'first': await release.wait()
                return TaskOutcome('completed', 'done')
        manager = TaskManager(Engine)
        first = manager.start('first')['task_id']
        second = manager.start('second', after_id=first)['task_id']
        await until(lambda: entered == ['first'])
        await until(lambda: manager.status(second)['state'] == 'waiting_dependency')
        release.set()
        await manager.wait()
        assert entered == ['first', 'second']
        assert not manager.start('invalid', after_id='unknown')['ok']
        assert not manager.desktop_gate.busy
    asyncio.run(scenario())


@pytest.mark.parametrize('outcome', ['failed', 'cancelled', 'needs_confirmation', 'needs_clarification'])
def test_failed_or_unconfirmed_dependency_never_starts_its_followup(outcome):
    async def scenario():
        calls = []
        class Engine:
            async def run(self, goal, cancel, on_step):
                calls.append(goal)
                return TaskOutcome(outcome, 'stopped')
        manager = TaskManager(Engine)
        first = manager.start('first')['task_id']
        second = manager.start('second', after_id=first)['task_id']
        await manager.wait()
        assert calls == ['first'] and manager.status(second)['state'] == 'blocked'
    asyncio.run(scenario())


def test_queued_pause_releases_resources_and_resumes_once():
    async def scenario():
        entered, release = [], asyncio.Event()
        class Engine:
            async def run(self, goal, cancel, on_step):
                entered.append(goal)
                if goal == 'first': await release.wait()
                return TaskOutcome('completed', 'done')
        manager = TaskManager(Engine)
        first = manager.start('first')['task_id']
        second = manager.start('second')['task_id']
        await until(lambda: entered == ['first'])
        assert not manager.pause(first)['ok']
        assert manager.pause(second)['ok']
        release.set()
        await until(lambda: manager.status(first)['state'] == 'completed')
        await until(lambda: not manager.desktop_gate.busy)
        assert entered == ['first'] and manager.status(second)['state'] == 'paused'
        assert manager.resume(second)['ok']
        await manager.wait()
        assert entered == ['first', 'second']
        assert not manager.resume(second)['ok']
    asyncio.run(scenario())


def test_paused_and_dependency_waiters_are_cancelled_on_shutdown():
    async def scenario():
        class Engine:
            async def run(self, goal, cancel, on_step):
                await until(cancel.is_set)
                return TaskOutcome('cancelled', 'stop')
        manager = TaskManager(Engine)
        first = manager.start('first')['task_id']
        second = manager.start('second', after_id=first)['task_id']
        manager.pause(second)
        manager.cancel_all()
        await manager.wait()
        assert manager.status(second)['state'] == 'cancelled' and not manager.desktop_gate.busy
    asyncio.run(scenario())


def test_pause_while_waiting_for_capacity_releases_the_desktop_lease_immediately():
    from livekit.agents import function_tool
    from jarvis.planner import ToolCall
    async def scenario():
        entered, release = [], asyncio.Event()
        @function_tool(name='web_answer', description='Fake research')
        async def research() -> dict:
            entered.append(True)
            await release.wait()
            return {'ok': True}
        def factory():
            return PlannerEngine(ScriptedModel([
                ModelTurn(tool_calls=[ToolCall(id='c', name='web_answer', arguments={})]),
                ModelTurn(text='done')]), [research])
        manager = TaskManager(factory)
        manager.start('research A', read_only=True)
        manager.start('research B', read_only=True)
        await until(lambda: len(entered) == 2)
        queued = manager.start('desktop')['task_id']
        await until(lambda: manager.desktop_gate.busy)
        assert manager.pause(queued)['ok']
        await until(lambda: not manager.desktop_gate.busy)
        assert len(entered) == 2 and manager.status(queued)['state'] == 'paused'
        manager.cancel(queued)
        release.set()
        await manager.wait()
    asyncio.run(scenario())


def test_real_voice_adapters_use_capabilities_without_native_registry_construction(tmp_path):
    async def scenario():
        registry = ToolRegistry.__new__(ToolRegistry)
        async def log(*args): pass
        registry._log_action = log
        registry.notes = NotesCapability(tmp_path/'notes')
        registry.checklists = ChecklistsCapability(tmp_path/'checklists.db')
        registry.calendar = SimpleNamespace(read_interval=lambda *a: ToolResult.success('read', 'ok', events=[]))
        registry.document = document([])
        registry.task_notifier = None
        tools = {t.info.name: t for t in registry.livekit_tools()}
        note_id = Path(registry.notes.save_note('Une idée', 'Projet').data['path']).name
        assert (await tools['search_notes']('idée'))['notes'][0]['note_id'] == note_id
        assert (await tools['read_note'](note_id))['ok']
        assert (await tools['append_note'](note_id, 'Suite'))['ok']
        assert (await tools['manage_checklist']('create', text='Bagages'))['list_id']
        assert (await tools['find_free_slots']('2026-10-19T09:00Z', '2026-10-19T18:00Z'))['slots']
        assert (await tools['calendar_conflicts']('2026-10-19T09:00Z', '2026-10-19T18:00Z'))['conflicts'] == []
        assert (await tools['compare_documents']('left', 'right'))['ok']
        assert (await tools['extract_document_actions']('left'))['ok']
        timer_id = (await tools['start_timer'](100, 'Essai'))['id']
        assert (await tools['list_timers']())['timers']
        assert (await tools['cancel_timer'](timer_id))['state'] == 'cancelled'
        assert not (await tools['pause_task']('missing'))['ok']
        assert not (await tools['resume_task']('missing'))['ok']
        await registry.timers.aclose()
    asyncio.run(scenario())
