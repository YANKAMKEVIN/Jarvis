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


class CalendarCapabilityTests(unittest.TestCase):
    def test_list_today_message(self):
        out = record("A", "s", "e", "C")
        cap = CalendarCapability(CalendarTools(runner=ok_runner(out)))
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
