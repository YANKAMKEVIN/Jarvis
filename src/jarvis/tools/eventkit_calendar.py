"""Fast, native calendar reads via EventKit (for the packaged Jarvis app).

A bare Python interpreter cannot obtain Calendar (TCC) access -- macOS only
prompts a binary that carries an NSCalendarsUsageDescription, i.e. a packaged
.app. So this is the correct backend for shipped Jarvis; in a dev CLI it reports
"not authorized" and the caller falls back to the (slower) AppleScript reader.

The pyobjc specifics live in _RealEventKitBackend; EventKitCalendarReader holds
the testable logic over an injectable backend.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from jarvis.tools.calendar import CalendarError


# EKAuthorizationStatus
NOT_DETERMINED = 0
AUTHORIZED_STATUSES = {3, 4}  # authorized, fullAccess (macOS 14+)


class EventKitBackend(Protocol):
    def authorization_status(self) -> int: ...
    def request_access(self) -> bool: ...
    def events_between(self, start_epoch: float, end_epoch: float) -> list[dict[str, Any]]: ...


class EventKitCalendarReader:
    def __init__(self, backend: EventKitBackend | None = None, clock=None):
        self._backend = backend if backend is not None else _RealEventKitBackend()
        self._clock = clock if clock is not None else time.time

    def read_today(self, day_offset: int = 0) -> dict[str, Any]:
        status = self._backend.authorization_status()
        if status not in AUTHORIZED_STATUSES:
            if status == NOT_DETERMINED:
                # Best effort: a packaged app gets the prompt here; a bare CLI
                # silently fails and stays not-determined.
                self._backend.request_access()
                status = self._backend.authorization_status()
            if status not in AUTHORIZED_STATUSES:
                raise CalendarError(
                    "L'acces au Calendrier n'est pas autorise. Active-le dans "
                    "Reglages Systeme > Confidentialite et securite > Calendriers.",
                    "calendar_not_authorized",
                )

        offset = int(day_offset)
        day_start = self._start_of_day(self._clock()) + offset * 86400.0
        day_end = day_start + 86400.0
        raw = self._backend.events_between(day_start, day_end)
        events = [
            {
                "title": item.get("title", ""),
                "start": item.get("start", ""),
                "end": item.get("end", ""),
                "calendar": item.get("calendar", ""),
            }
            for item in raw
        ]
        return {"day_offset": offset, "events": events, "event_count": len(events)}

    @staticmethod
    def _start_of_day(epoch: float) -> float:
        local = time.localtime(epoch)
        midnight = time.struct_time(
            (local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0,
             local.tm_wday, local.tm_yday, local.tm_isdst)
        )
        return time.mktime(midnight)


class _RealEventKitBackend:
    """pyobjc-backed EventKit access. Exercised in the packaged app; in a dev
    CLI authorization stays not-determined and request_access returns False."""

    def __init__(self):
        try:
            import EventKit  # noqa: F401
            import Foundation  # noqa: F401
        except Exception as error:  # pragma: no cover - import guard
            raise CalendarError(
                f"EventKit indisponible : {error}", "eventkit_unavailable"
            )
        self._EventKit = EventKit
        self._Foundation = Foundation
        self._store = EventKit.EKEventStore.alloc().init()

    def authorization_status(self) -> int:  # pragma: no cover - needs macOS TCC
        return int(self._EventKit.EKEventStore.authorizationStatusForEntityType_(0))

    def request_access(self) -> bool:  # pragma: no cover - needs macOS TCC
        import threading

        done = threading.Event()
        result = {"ok": False}

        def handler(ok, err):
            result["ok"] = bool(ok)
            done.set()

        if hasattr(self._store, "requestFullAccessToEventsWithCompletion_"):
            self._store.requestFullAccessToEventsWithCompletion_(handler)
        else:
            self._store.requestAccessToEntityType_completion_(0, handler)

        run_loop = self._Foundation.NSRunLoop.currentRunLoop()
        deadline = time.time() + 20
        while not done.is_set() and time.time() < deadline:
            run_loop.runUntilDate_(
                self._Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.3)
            )
        return result["ok"]

    def events_between(self, start_epoch, end_epoch):  # pragma: no cover - needs macOS TCC
        F = self._Foundation
        start = F.NSDate.dateWithTimeIntervalSince1970_(start_epoch)
        end = F.NSDate.dateWithTimeIntervalSince1970_(end_epoch)
        predicate = self._store.predicateForEventsWithStartDate_endDate_calendars_(
            start, end, None
        )
        events = self._store.eventsMatchingPredicate_(predicate) or []
        out = []
        for event in events:
            cal = event.calendar()
            out.append(
                {
                    "title": str(event.title() or ""),
                    "start": str(event.startDate() or ""),
                    "end": str(event.endDate() or ""),
                    "calendar": str(cal.title()) if cal is not None else "",
                }
            )
        return out
