import json
import time

import pytest

from jarvis.capabilities.usage import UsageCapability, _human
from jarvis.usage.store import UsageStore

# A fixed "now" so period windows are deterministic.
NOW = time.mktime((2026, 10, 20, 12, 0, 0, 0, 0, -1))


def _line(uuid, ts, model="claude-opus-4-8", out=20, session="s1"):
    return json.dumps({
        "type": "assistant", "uuid": uuid, "timestamp": ts, "sessionId": session,
        "message": {"model": model, "usage": {
            "input_tokens": 10, "output_tokens": out,
            "cache_creation_input_tokens": 100, "cache_read_input_tokens": 200,
            "output_tokens_details": {"thinking_tokens": 5},
        }},
    }) + "\n"


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


@pytest.fixture
def cap(tmp_path):
    projects = tmp_path / "projects"
    (projects / "-tmp-Alpha").mkdir(parents=True)
    f = projects / "-tmp-Alpha" / "session.jsonl"
    # two events today, one 10 days ago
    with f.open("w") as fh:
        fh.write(_line("a", _iso(NOW - 3600)))
        fh.write(_line("b", _iso(NOW - 7200), model="claude-sonnet-5"))
        fh.write(_line("old", _iso(NOW - 10 * 86400)))
    store = UsageStore(db_path=tmp_path / "u.db", projects_dir=projects, clock=lambda: NOW)
    return UsageCapability(store=store, clock=lambda: NOW)


def test_human_formatting():
    assert _human(28_800_000) == "28,8 M"
    assert _human(12_200_000_000) == "12,2 Md"
    assert _human(5_400) == "5 k"
    assert _human(42) == "42"


def test_overview_today_counts_only_today(cap):
    r = cap.overview("today")
    assert r.ok and r.data["events"] == 2          # the 10-day-old one excluded
    assert r.data["output"] == 40
    assert "générés" in r.message


def test_overview_all_includes_history(cap):
    r = cap.overview("all")
    assert r.data["events"] == 3


def test_by_model_lists_each(cap):
    r = cap.by_model("30d")
    models = {m["model"] for m in r.data["models"]}
    assert models == {"claude-opus-4-8", "claude-sonnet-5"}


def test_by_project_label(cap):
    r = cap.by_project("30d")
    assert r.data["projects"][0]["project"] == "Alpha"


def test_trend_has_series(cap):
    r = cap.trend(days=14)
    assert r.ok and len(r.data["series"]) >= 1
    assert all("day" in d and "total_tokens" in d for d in r.data["series"])


def test_compare_against_previous_window(cap):
    r = cap.compare("7d")
    assert r.ok
    assert r.data["current"]["total_tokens"] >= 0
    assert "tokens" in r.message


def test_empty_period_is_graceful(cap):
    r = cap.overview("yesterday")   # nothing logged yesterday in the fixture
    assert r.ok and r.data["events"] == 0
    assert "Aucune" in r.message


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
