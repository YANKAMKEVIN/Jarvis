import unittest

from jarvis.capabilities.calendar import CalendarCapability
from jarvis.tools.calendar import FIELD_SEP, RECORD_SEP, CalendarError, CalendarTools


def ok_runner(stdout):
    return lambda script: (0, stdout, "")


def fail_runner(stderr="boom"):
    return lambda script: (1, "", stderr)


def record(title, start, end, cal):
    return FIELD_SEP.join([title, start, end, cal]) + RECORD_SEP


class CalendarToolsTests(unittest.TestCase):
    def test_parses_events(self):
        out = (
            record("Reunion equipe", "lundi 09:00", "lundi 10:00", "Travail")
            + record("Dejeuner", "lundi 12:30", "lundi 13:30", "Perso")
        )
        tools = CalendarTools(runner=ok_runner(out))

        state = tools.list_events_today()

        self.assertEqual(state["event_count"], 2)
        self.assertEqual(state["events"][0]["title"], "Reunion equipe")
        self.assertEqual(state["events"][0]["calendar"], "Travail")
        self.assertEqual(state["events"][1]["title"], "Dejeuner")

    def test_empty_calendar(self):
        state = CalendarTools(runner=ok_runner("")).list_events_today()
        self.assertEqual(state["event_count"], 0)

    def test_read_failure_raises(self):
        with self.assertRaises(CalendarError):
            CalendarTools(runner=fail_runner()).list_events_today()

    def test_create_event_builds_components_and_succeeds(self):
        captured = {}

        def runner(script):
            captured["script"] = script
            return (0, "ok", "")

        from datetime import datetime
        tools = CalendarTools(runner=runner)
        state = tools.create_event(
            "Point budget",
            datetime(2026, 10, 16, 9, 0),
            datetime(2026, 10, 16, 10, 0),
        )

        self.assertTrue(state["command_executed"])
        self.assertIn("set month of s to 10", captured["script"])
        self.assertIn("set day of s to 16", captured["script"])
        self.assertIn("Point budget", captured["script"])

    def test_create_failure_raises(self):
        from datetime import datetime
        tools = CalendarTools(runner=fail_runner("no calendar"))
        with self.assertRaises(CalendarError):
            tools.create_event("x", datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10))


class FakeEventKitBackend:
    def __init__(self, status=3, events=None, request_becomes=3):
        self._status = status
        self._events = events or []
        self._request_becomes = request_becomes
        self.requested = False
        self.read_count = 0

    def authorization_status(self):
        return self._status

    def request_access(self):
        self.requested = True
        self._status = self._request_becomes
        return self._status in (3, 4)

    def events_between(self, start_epoch, end_epoch):
        self.read_count += 1
        return list(self._events)


class EventKitReaderTests(unittest.TestCase):
    def _reader(self, backend):
        from jarvis.tools.eventkit_calendar import EventKitCalendarReader
        return EventKitCalendarReader(backend=backend)

    def test_authorized_reads_events(self):
        backend = FakeEventKitBackend(status=3, events=[
            {"title": "RDV", "start": "s", "end": "e", "calendar": "Perso"},
        ])
        state = self._reader(backend).read_today()
        self.assertEqual(state["event_count"], 1)
        self.assertEqual(state["events"][0]["title"], "RDV")
        self.assertFalse(backend.requested)  # already authorized

    def test_denied_raises_not_authorized(self):
        backend = FakeEventKitBackend(status=2)
        with self.assertRaises(CalendarError) as ctx:
            self._reader(backend).read_today()
        self.assertEqual(ctx.exception.code, "calendar_not_authorized")

    def test_not_determined_requests_then_reads(self):
        backend = FakeEventKitBackend(status=0, request_becomes=3, events=[
            {"title": "A", "start": "s", "end": "e", "calendar": "C"},
        ])
        state = self._reader(backend).read_today()
        self.assertTrue(backend.requested)
        self.assertEqual(state["event_count"], 1)

    def test_not_determined_request_denied_raises(self):
        backend = FakeEventKitBackend(status=0, request_becomes=2)
        with self.assertRaises(CalendarError) as ctx:
            self._reader(backend).read_today()
        self.assertEqual(ctx.exception.code, "calendar_not_authorized")


class CalendarEventKitFallbackTests(unittest.TestCase):
    def test_uses_eventkit_when_authorized(self):
        backend = FakeEventKitBackend(status=3, events=[
            {"title": "EK", "start": "s", "end": "e", "calendar": "C"},
        ])
        from jarvis.tools.eventkit_calendar import EventKitCalendarReader
        # AppleScript runner that fails loudly if ever used.
        def boom_runner(script):
            raise AssertionError("AppleScript should not be used when EventKit works")
        cap = CalendarCapability(
            calendar_tools=CalendarTools(runner=boom_runner),
            events_reader=EventKitCalendarReader(backend=backend),
        )
        result = cap.list_today()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["events"][0]["title"], "EK")

    def test_falls_back_to_applescript_when_not_authorized(self):
        from jarvis.tools.eventkit_calendar import EventKitCalendarReader
        backend = FakeEventKitBackend(status=2)  # denied
        cap = CalendarCapability(
            calendar_tools=CalendarTools(runner=ok_runner(record("AS", "s", "e", "C"))),
            events_reader=EventKitCalendarReader(backend=backend),
        )
        result = cap.list_today()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["events"][0]["title"], "AS")  # AppleScript path


class CalendarCapabilityTests(unittest.TestCase):
    def test_list_today_message(self):
        from jarvis.tools.eventkit_calendar import EventKitCalendarReader
        out = record("A", "s", "e", "C")
        # Denied EventKit -> AppleScript fallback path under test.
        cap = CalendarCapability(
            CalendarTools(runner=ok_runner(out)),
            events_reader=EventKitCalendarReader(backend=FakeEventKitBackend(status=2)),
        )
        result = cap.list_today()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["event_count"], 1)

    def test_create_requires_valid_range(self):
        cap = CalendarCapability(CalendarTools(runner=ok_runner("ok")))
        result = cap.create_event("RDV", "2026-10-16T10:00", "2026-10-16T09:00")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_range")

    def test_create_rejects_bad_dates(self):
        cap = CalendarCapability(CalendarTools(runner=ok_runner("ok")))
        result = cap.create_event("RDV", "pas une date", "2026-10-16T10:00")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_datetime")

    def test_create_success(self):
        cap = CalendarCapability(CalendarTools(runner=ok_runner("ok")))
        result = cap.create_event("RDV", "2026-10-16T09:00", "2026-10-16T10:00")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["title"], "RDV")


if __name__ == "__main__":
    unittest.main()
