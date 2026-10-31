import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jarvis.activity import (ACTIVITY_RETENTION_SECONDS, ActivityStore, default_store,
                             log_event)
from jarvis.insights.detector import Insight, InsightMonitor


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class ActivityStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.store = ActivityStore(Path(self.tmp.name) / "a" / "activity.db", clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_is_private(self):
        self.store.record("tool", "get_time")
        self.assertEqual(stat.S_IMODE(os.stat(self.store.path).st_mode), 0o600)

    def test_top_counts_names_most_used_first(self):
        for name in ("open_app", "get_time", "open_app", "open_app", "get_time", "dance_avatar"):
            self.clock.now += 1
            self.store.record("tool", name)
        top = self.store.top("tool")
        self.assertEqual([(t["name"], t["count"]) for t in top],
                         [("open_app", 3), ("get_time", 2), ("dance_avatar", 1)])
        self.assertEqual(self.store.count("tool"), 6)
        self.assertEqual(self.store.count("wake"), 0)

    def test_since_filters_old_events(self):
        self.store.record("wake", "hey_jarvis")
        self.clock.now += 3600
        self.store.record("wake", "hey_jarvis")
        self.assertEqual(self.store.count("wake", since=self.clock.now - 60), 1)

    def test_recent_keeps_detail_and_level_newest_first(self):
        self.store.record("alert", "Mémoire", "Mémoire à 91 %", "warning")
        self.clock.now += 1
        self.store.record("alert", "Tokens", "Journée chargée", "info")
        rows = self.store.recent("alert")
        self.assertEqual([r["name"] for r in rows], ["Tokens", "Mémoire"])
        self.assertEqual(rows[1]["detail"], "Mémoire à 91 %")
        self.assertEqual(rows[1]["level"], "warning")

    def test_retention_drops_events_older_than_thirty_days(self):
        self.store.record("tool", "get_time")
        self.clock.now += ACTIVITY_RETENTION_SECONDS + 1
        self.assertEqual(self.store.count("tool"), 0)

    def test_unknown_kind_and_empty_name(self):
        with self.assertRaises(ValueError):
            self.store.record("secret", "x")
        self.store.record("tool", "   ")
        self.assertEqual(self.store.count("tool"), 0)

    def test_clear_reports_removed_rows(self):
        self.store.record("tool", "a")
        self.store.record("wake", "hey_jarvis")
        self.assertEqual(self.store.clear(), 2)
        self.assertEqual(self.store.count("tool"), 0)

    def test_log_event_records_and_never_raises(self):
        with mock.patch.dict(os.environ, {"JARVIS_ACTIVITY_DISABLED": ""}):
            log_event("tool", "get_time", store=self.store)
            broken = mock.Mock()
            broken.record.side_effect = OSError("disk full")
            log_event("tool", "x", store=broken)  # no exception
        self.assertEqual(self.store.count("tool"), 1)

    def test_log_event_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"JARVIS_ACTIVITY_DISABLED": "1"}):
            log_event("tool", "x", store=self.store)
        self.assertEqual(self.store.count("tool"), 0)

    def test_default_store_is_isolated_in_tests(self):
        self.assertNotIn("Library", str(default_store().path))


class AlertLoggingTests(unittest.TestCase):
    def test_monitor_logs_each_fresh_alert_once(self):
        insight = Insight("cpu_high", "warning", "Processeur", "CPU à 95 %", 0.0)
        detector = mock.Mock()
        detector.scan.return_value = [insight]
        monitor = InsightMonitor(detector, clock=lambda: 10.0)
        with mock.patch("jarvis.insights.detector.log_event") as logged:
            monitor.tick()
            monitor.tick()  # still in cooldown: not fired, not logged again
        logged.assert_called_once_with("alert", "Processeur", "CPU à 95 %", "warning")


if __name__ == "__main__":
    unittest.main()
