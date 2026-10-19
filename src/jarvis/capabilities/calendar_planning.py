"""Read-only interval analysis. Unreadable dates never become free time."""
from datetime import datetime
from jarvis.capabilities.results import ToolResult


def aware(value):
    if not isinstance(value, str):
        raise ValueError('invalid_datetime')
    result = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('timezone_required')
    return result


class CalendarPlanning:
    def __init__(self, calendar):
        self.calendar = calendar

    def analyze(self, operation, start, end, duration_minutes=30):
        action = 'find_free_slots' if operation == 'free' else 'calendar_conflicts'
        try:
            left, right = aware(start), aware(end)
            lower, upper = left.timestamp(), right.timestamp()
            if not 0 < upper-lower <= 7*86400 or operation not in {'free', 'conflicts'}:
                raise ValueError('invalid_range')
            if operation == 'free' and (type(duration_minutes) is not int or not 1 <= duration_minutes <= 1440):
                raise ValueError('invalid_duration')
        except (ValueError, TypeError, OverflowError):
            return ToolResult.failure(action, 'Dates ISO avec fuseau obligatoire, intervalle de sept jours maximum et duree valide.', 'invalid_range')
        result = self.calendar.read_interval(lower, upper)
        if not result.ok:
            return ToolResult.failure(action, result.message, result.error_code)
        events = []
        try:
            raw_events = result.data['events']
            if not isinstance(raw_events, list) or len(raw_events) > 1000:
                raise ValueError('incomplete_calendar')
            for index, event in enumerate(raw_events):
                begin, finish = aware(event['start']).timestamp(), aware(event['end']).timestamp()
                if finish <= begin:
                    raise ValueError('invalid_event')
                if begin < upper and finish > lower:
                    events.append((max(begin, lower), min(finish, upper), str(event.get('title', 'Evenement'))[:200], index))
        except (KeyError, ValueError, TypeError, OverflowError):
            return ToolResult.failure(action, 'Des horaires sont incomplets ou illisibles ; aucune disponibilite fiable ne peut etre calculee.', 'incomplete_calendar')
        events.sort()
        iso = lambda epoch: datetime.fromtimestamp(epoch, left.tzinfo).isoformat(timespec='minutes')
        rows = []
        if operation == 'free':
            cursor = lower
            for begin, finish, _, _ in events:
                if begin-cursor >= duration_minutes*60:
                    rows.append({'start': iso(cursor), 'end': iso(begin)})
                cursor = max(cursor, finish)
            if upper-cursor >= duration_minutes*60:
                rows.append({'start': iso(cursor), 'end': iso(upper)})
            return ToolResult.success(action, f'{len(rows)} plage(s) disponible(s), sans reservation automatique.',
                                      slots=rows[:20], total=len(rows), truncated=len(rows)>20)
        for i, first in enumerate(events):
            for second in events[i+1:]:
                if second[0] >= first[1]:
                    break
                rows.append({'first': first[2], 'second': second[2], 'start': iso(max(first[0], second[0])), 'end': iso(min(first[1], second[1]))})
                if len(rows) == 50:
                    return ToolResult.success(action, 'Au moins 50 chevauchements. Affichage limite.', conflicts=rows, truncated=True)
        return ToolResult.success(action, f'{len(rows)} chevauchement(s) dans l’intervalle lu.', conflicts=rows, truncated=False)
