"""Session timers: monotonic deadlines, independent IDs, explicit shutdown."""
import asyncio
import math
from time import monotonic
from uuid import uuid4
from jarvis.capabilities.results import ToolResult


class TimerService:
    def __init__(self, notify=None, clock=monotonic, sleep=asyncio.sleep):
        self.notify, self.clock, self.sleep = notify, clock, sleep
        self.timers = {}
        self.closed = False

    def start(self, seconds, label='Minuteur'):
        if self.closed:
            return ToolResult.failure('start_timer', 'La session se ferme.', 'session_stopping')
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 1 <= seconds <= 86400:
            return ToolResult.failure('start_timer', 'Duree entre 1 seconde et 24 heures.', 'invalid_duration')
        if not isinstance(label, str) or not label.strip() or len(label) > 100:
            return ToolResult.failure('start_timer', 'Nom de minuteur invalide.', 'invalid_label')
        if sum(t['state'] == 'running' for t in self.timers.values()) >= 10:
            return ToolResult.failure('start_timer', 'Dix minuteurs sont deja actifs.', 'limit_reached')
        while len(self.timers) >= 20:
            oldest = next((key for key, t in self.timers.items() if t['task'].done()), None)
            if oldest is None:
                return ToolResult.failure('start_timer', 'Attendez la fin des annonces de minuteurs.', 'limit_reached')
            del self.timers[oldest]
        key = uuid4().hex
        timer = {'id': key, 'label': label.strip(), 'seconds': seconds, 'deadline': self.clock()+seconds, 'state': 'running'}
        self.timers[key] = timer
        timer['task'] = asyncio.create_task(self._run(timer))
        return ToolResult.success('start_timer', 'Minuteur lance pour cette session. Fermer Jarvis l’annule.', **self._view(timer))

    def _view(self, timer):
        return {key: timer[key] for key in ('id', 'label', 'seconds', 'state')} | {
            'remaining_seconds': max(0, math.ceil(timer['deadline'] - self.clock())) if timer['state'] == 'running' else 0}

    async def _run(self, timer):
        try:
            while not self.closed and self.clock() < timer['deadline']:
                await self.sleep(timer['deadline'] - self.clock())
            if self.closed or timer['state'] != 'running':
                return
            timer['state'] = 'completed'
            if self.notify is not None:
                await self.notify(self._view(timer))
        except asyncio.CancelledError:
            if timer['state'] == 'running':
                timer['state'] = 'cancelled'
        except Exception:
            # The deadline has passed even when voice notification is unavailable.
            timer['notification_failed'] = True

    def status(self):
        return ToolResult.success('list_timers', 'Minuteurs de cette session.', timers=[self._view(t) for t in self.timers.values()])

    def cancel(self, timer_id):
        timer = self.timers.get(timer_id)
        if timer is None:
            return ToolResult.failure('cancel_timer', 'Minuteur introuvable.', 'timer_not_found')
        if timer['state'] == 'running':
            timer['state'] = 'cancelled'
            timer['task'].cancel()
        return ToolResult.success('cancel_timer', 'Etat du minuteur.', **self._view(timer))

    async def aclose(self):
        self.closed = True
        for timer in self.timers.values():
            if timer['state'] == 'running':
                timer['state'] = 'cancelled'
            timer['task'].cancel()
        await asyncio.gather(*(t['task'] for t in self.timers.values()), return_exceptions=True)
