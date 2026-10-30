import types

import pytest

from jarvis.metrics.sampler import MetricsSampler
from jarvis.metrics.store import MetricsStore
from jarvis.tools.system_metrics import SystemMetricsProbe


class FakePsutil:
    def __init__(self, cpu=23.0):
        self._cpu = cpu

    def cpu_percent(self, interval=None):
        return self._cpu

    def virtual_memory(self):
        return types.SimpleNamespace(percent=61.0, used=9_800_000_000, total=16_000_000_000)

    def swap_memory(self):
        return types.SimpleNamespace(percent=4.0)

    def disk_usage(self, path):
        return types.SimpleNamespace(percent=78.0, used=400_000_000_000, total=512_000_000_000)

    def net_io_counters(self):
        return types.SimpleNamespace(bytes_sent=1000, bytes_recv=2000)

    def sensors_battery(self):
        return types.SimpleNamespace(percent=88.0, power_plugged=True)

    def process_iter(self, attrs=None):
        data = [
            {"pid": 1, "name": "Xcode", "memory_percent": 12.0},
            {"pid": 2, "name": "Chrome", "memory_percent": 25.0},
            {"pid": 3, "name": "Finder", "memory_percent": 3.0},
        ]
        return [types.SimpleNamespace(info=d) for d in data]


# --- probe ------------------------------------------------------------------

def test_snapshot_shape():
    probe = SystemMetricsProbe(psutil_module=FakePsutil(), clock=lambda: 1000.0)
    s = probe.snapshot(cpu_interval=None)
    assert s["cpu"] == 23.0 and s["mem"] == 61.0 and s["disk"] == 78.0
    assert s["battery"] == 88.0 and s["power_plugged"] is True
    assert s["ts"] == 1000.0 and s["mem_total"] == 16_000_000_000


def test_top_processes_by_memory_sorted():
    probe = SystemMetricsProbe(psutil_module=FakePsutil())
    rows = probe.top_processes(by="memory", limit=2)
    assert [r["name"] for r in rows] == ["Chrome", "Xcode"]


def test_app_name_folds_helpers_and_claude_code():
    from jarvis.tools.system_metrics import app_name

    chrome = ("/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework"
              ".framework/Helpers/Google Chrome Helper (Renderer).app/Contents/MacOS/x")
    assert app_name("Google Chrome Helper (Renderer)", chrome) == "Google Chrome"
    assert app_name("2.1.303", "/Users/me/.local/bin/claude") == "Claude Code"
    assert app_name("claude", "/Users/me/Library/Application Support/Claude/claude-code/"
                              "2.1.309/abc/claude.app/Contents/MacOS/claude") == "Claude Code"
    assert app_name("Python", None) == "Python"


def test_top_apps_sums_memory_per_app():
    class AppsPsutil(FakePsutil):
        def process_iter(self, attrs=None):
            mem = lambda n: types.SimpleNamespace(rss=n)
            data = [
                {"pid": 1, "name": "Google Chrome", "memory_info": mem(1_000_000_000),
                 "exe": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"},
                {"pid": 2, "name": "Google Chrome Helper (Renderer)", "memory_info": mem(600_000_000),
                 "exe": "/Applications/Google Chrome.app/Contents/Frameworks/H.app/Contents/MacOS/H"},
                {"pid": 3, "name": "Xcode", "memory_info": mem(1_200_000_000),
                 "exe": "/Applications/Xcode.app/Contents/MacOS/Xcode"},
                {"pid": 4, "name": "kernel_task", "memory_info": None, "exe": None},
            ]
            return [types.SimpleNamespace(info=d) for d in data]

    rows = SystemMetricsProbe(psutil_module=AppsPsutil()).top_apps(limit=5)
    assert [(r["name"], r["bytes"], r["processes"]) for r in rows] == [
        ("Google Chrome", 1_600_000_000, 2), ("Xcode", 1_200_000_000, 1)]
    assert rows[0]["value"] == 10.0  # 1.6 GB of the fake 16 GB


def test_probe_without_psutil_reports_unavailable():
    probe = SystemMetricsProbe()
    probe.ps = None  # simulate an environment without psutil
    assert probe.available() is False
    with pytest.raises(RuntimeError):
        probe.snapshot()


# --- store ------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return MetricsStore(db_path=tmp_path / "m.db", clock=lambda: 10_000.0)


def _sample(ts, cpu, mem=50.0):
    return {"ts": ts, "cpu": cpu, "mem": mem, "mem_used": 1, "mem_total": 2,
            "swap": 0.0, "disk": 70.0, "disk_used": 1, "disk_total": 2,
            "net_sent": 0, "net_recv": 0, "load1": 1.5, "battery": 90.0}


def test_record_latest_and_count(store):
    store.record(_sample(9000, 20))
    store.record(_sample(9500, 40))
    assert store.count() == 2
    assert store.latest()["cpu"] == 40


def test_history_buckets_average(store):
    # two samples in the same bucket average together
    for ts, cpu in [(9000, 20), (9100, 40), (9700, 80)]:
        store.record(_sample(ts, cpu))
    series = store.history("cpu", since=8800, until=10_000, buckets=2)
    assert len(series) >= 1
    assert all(0 <= p["value"] <= 100 for p in series)


def test_summary_stats(store):
    for ts, cpu in [(9000, 20), (9500, 60)]:
        store.record(_sample(ts, cpu))
    summ = store.summary("cpu", since=8800, until=10_000)
    assert summ["samples"] == 2 and summ["avg"] == 40.0 and summ["max"] == 60.0


def test_history_rejects_unknown_metric(store):
    with pytest.raises(ValueError):
        store.history("gpu")


def test_retention_drops_old_samples(tmp_path):
    s = MetricsStore(db_path=tmp_path / "m.db", clock=lambda: 10_000_000.0)
    s.record(_sample(10_000_000 - 1_000_000, 30))  # ~11.5 days old: kept
    # Force an old row then reconnect to trigger retention sweep.
    s.record(_sample(100.0, 99))                    # ancient: swept on next connect
    assert s.count() == 1


# --- sampler ----------------------------------------------------------------

def test_sampler_records_a_sample(store):
    probe = SystemMetricsProbe(psutil_module=FakePsutil(), clock=lambda: 10_000.0)
    sampler = MetricsSampler(probe=probe, store=store)
    sample = sampler.tick()
    assert sample is not None
    assert store.count() == 1


def test_sampler_noop_without_psutil(store):
    probe = SystemMetricsProbe()
    probe.ps = None  # simulate an environment without psutil
    sampler = MetricsSampler(probe=probe, store=store)
    assert sampler.tick() is None
    assert store.count() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
