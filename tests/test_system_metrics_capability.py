import types

import pytest

from jarvis.capabilities.system_metrics import SystemMetricsCapability
from jarvis.metrics.store import MetricsStore
from jarvis.tools.system_metrics import SystemMetricsProbe
from tests.test_system_metrics import FakePsutil


@pytest.fixture
def cap(tmp_path):
    probe = SystemMetricsProbe(psutil_module=FakePsutil(), clock=lambda: 10_000.0)
    store = MetricsStore(db_path=tmp_path / "m.db", clock=lambda: 10_000.0)
    return SystemMetricsCapability(probe=probe, store=store, clock=lambda: 10_000.0), store


def test_snapshot_message(cap):
    c, _ = cap
    r = c.snapshot()
    assert r.ok
    assert "Processeur 23 %" in r.message and "mémoire 61 %" in r.message
    assert r.data["cpu"] == 23.0


def test_top_processes(cap):
    c, _ = cap
    r = c.top_processes(by="memory", limit=2)
    assert r.ok and r.data["processes"][0]["name"] == "Chrome"


def test_history_empty_is_graceful(cap):
    c, _ = cap
    r = c.history("cpu", "24h")
    assert r.ok and r.data["series"] == []
    assert "Pas encore" in r.message


def test_history_with_samples(cap):
    c, store = cap
    for ts, cpu in [(9000, 20.0), (9500, 60.0)]:
        store.record({"ts": ts, "cpu": cpu, "mem": 50.0, "mem_used": 1, "mem_total": 2,
                      "swap": 0.0, "disk": 70.0, "disk_used": 1, "disk_total": 2,
                      "net_sent": 0, "net_recv": 0, "load1": 1.0, "battery": 90.0})
    r = c.history("processeur", "24h")   # alias resolves to cpu
    assert r.ok and r.data["metric"] == "cpu"
    assert r.data["summary"]["max"] == 60.0


def test_every_gauge_metric_resolves_to_itself(cap):
    # Canonical names must round-trip, or history(metric) silently reads cpu.
    from jarvis.metrics.store import GAUGE_METRICS

    c, _ = cap
    for name in GAUGE_METRICS:
        assert c._metric(name) == name


def test_history_mem_reads_mem_not_cpu(cap):
    c, store = cap
    for ts, cpu, mem in [(9000, 10.0, 80.0), (9500, 12.0, 82.0)]:
        store.record({"ts": ts, "cpu": cpu, "mem": mem, "mem_used": 1, "mem_total": 2,
                      "swap": 0.0, "disk": 70.0, "disk_used": 1, "disk_total": 2,
                      "net_sent": 0, "net_recv": 0, "load1": 1.0, "battery": 90.0})
    r = c.history("mem", "24h")
    assert r.data["metric"] == "mem"
    assert r.data["summary"]["max"] == 82.0   # mem values, not cpu's 12


def test_snapshot_unavailable():
    probe = SystemMetricsProbe()
    probe.ps = None
    c = SystemMetricsCapability(probe=probe, store=MetricsStore(db_path="/tmp/none.db"))
    r = c.snapshot()
    assert not r.ok and r.error_code == "metrics_unavailable"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
