import time

from jarvis.capabilities.insights import InsightsCapability
from jarvis.insights.detector import InsightDetector, InsightMonitor, Thresholds
from jarvis.metrics.store import MetricsStore

NOW = 1_800_000_000.0


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


def sample(ts, cpu=20.0, mem=50.0, disk=60.0):
    return {"ts": ts, "cpu": cpu, "mem": mem, "mem_used": 8, "mem_total": 16,
            "swap": 0.0, "disk": disk, "disk_used": 900_000_000_000,
            "disk_total": 1_000_000_000_000, "net_sent": 0, "net_recv": 0,
            "load1": 1.0, "battery": 80.0}


def fill(store, clock, **values):
    for i in range(10):  # 10 samples over the last ~3 minutes
        store.record(sample(clock.now - i * 20, **values))


class FakeProbe:
    def top_processes(self, by="cpu", limit=1):
        return [{"name": "Xcode", "value": 240.0}]


class FakeUsage:
    def __init__(self, days):
        self.days = days
        self.ingested = 0

    def ingest(self):
        self.ingested += 1

    def by_day(self, days=15, until=None):
        return self.days


def today(clock):
    return time.strftime("%Y-%m-%d", time.localtime(clock.now))


def detector(tmp_path, clock, usage=None):
    store = MetricsStore(db_path=tmp_path / "m.db", clock=clock)
    return InsightDetector(metrics=store, usage=usage, probe=FakeProbe(), clock=clock), store


def test_calm_machine_has_no_insight(tmp_path):
    clock = Clock()
    d, store = detector(tmp_path, clock)
    fill(store, clock)
    assert d.scan() == []


def test_sustained_cpu_names_the_culprit(tmp_path):
    clock = Clock()
    d, store = detector(tmp_path, clock)
    fill(store, clock, cpu=95.0)
    found = d.machine_insights()
    assert [i.kind for i in found] == ["cpu_sustained"]
    assert "95 %" in found[0].message and "Xcode" in found[0].message


def test_a_short_spike_is_not_enough(tmp_path):
    clock = Clock()
    d, store = detector(tmp_path, clock)
    for i in range(3):  # under min_samples
        store.record(sample(clock.now - i * 20, cpu=99.0))
    assert d.machine_insights() == []


def test_memory_and_disk(tmp_path):
    clock = Clock()
    d, store = detector(tmp_path, clock)
    fill(store, clock, mem=93.0, disk=95.0)
    kinds = {i.kind: i for i in d.machine_insights()}
    assert set(kinds) == {"mem_pressure", "disk_full"}
    assert "100 Go" in kinds["disk_full"].message


def test_stale_disk_reading_is_ignored(tmp_path):
    clock = Clock()
    d, store = detector(tmp_path, clock)
    store.record(sample(clock.now - 3600, disk=99.0))
    assert d.machine_insights() == []


def test_token_spike_against_own_baseline(tmp_path):
    clock = Clock()
    past = [{"day": f"2026-01-0{i}", "total_tokens": 10_000_000} for i in range(1, 8)]
    usage = FakeUsage(past + [{"day": today(clock), "total_tokens": 35_000_000}])
    d, _ = detector(tmp_path, clock, usage)
    [insight] = d.token_insights()
    assert insight.kind == "token_day_spike" and insight.once
    assert "3,5 fois" in insight.message
    assert usage.ingested == 1


def test_token_rule_needs_history_and_volume(tmp_path):
    clock = Clock()
    short = [{"day": "2026-01-01", "total_tokens": 1_000_000},
             {"day": today(clock), "total_tokens": 90_000_000}]
    d, _ = detector(tmp_path, clock, FakeUsage(short))
    assert d.token_insights() == []
    past = [{"day": f"2026-01-0{i}", "total_tokens": 100_000} for i in range(1, 8)]
    small = FakeUsage(past + [{"day": today(clock), "total_tokens": 1_000_000}])
    d, _ = detector(tmp_path, clock, small)
    assert d.token_insights() == []  # 10x, but under the absolute floor


def test_monitor_cooldown_and_notifier(tmp_path):
    clock = Clock()
    d, store = detector(tmp_path, clock)
    fill(store, clock, cpu=95.0)
    seen = []
    m = InsightMonitor(d, notifier=seen.append, cooldown_seconds=3600, clock=clock)
    assert [i.kind for i in m.tick()] == ["cpu_sustained"]
    clock.now += 300
    fill(store, clock, cpu=95.0)
    assert m.tick() == []  # still hot, already announced
    clock.now += 3600
    fill(store, clock, cpu=95.0)
    assert len(m.tick()) == 1
    assert len(seen) == 2 and m.recent(1)[0].kind == "cpu_sustained"


def test_monitor_fires_daily_token_alert_once(tmp_path):
    clock = Clock()
    past = [{"day": f"2026-01-0{i}", "total_tokens": 10_000_000} for i in range(1, 8)]
    usage = FakeUsage(past + [{"day": today(clock), "total_tokens": 50_000_000}])
    d, _ = detector(tmp_path, clock, usage)
    m = InsightMonitor(d, cooldown_seconds=60, token_every_seconds=0, clock=clock)
    assert len(m.tick()) == 1
    clock.now += 120  # past the cooldown, same day
    assert m.tick() == []


def test_monitor_survives_detector_errors():
    class Boom:
        def scan(self, include_tokens=True):
            raise RuntimeError("db locked")
    assert InsightMonitor(Boom()).tick() == []


def test_capability_reports_calm_and_anomalies(tmp_path):
    clock = Clock()
    d, store = detector(tmp_path, clock)
    cap = InsightsCapability(d)
    r = cap.check()
    assert r.ok and r.data["insights"] == [] and "Rien d'anormal" in r.message
    fill(store, clock, cpu=97.0)
    r = cap.check()
    assert r.ok and r.data["insights"][0]["kind"] == "cpu_sustained"


def test_thresholds_are_tunable(tmp_path):
    clock = Clock()
    store = MetricsStore(db_path=tmp_path / "m.db", clock=clock)
    fill(store, clock, cpu=70.0)
    d = InsightDetector(metrics=store, thresholds=Thresholds(cpu_percent=60.0), clock=clock)
    assert [i.kind for i in d.machine_insights()] == ["cpu_sustained"]
    assert "Le plus gourmand" not in d.machine_insights()[0].message  # no probe
