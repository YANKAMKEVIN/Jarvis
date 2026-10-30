import json
import time

import pytest

from jarvis.usage.store import (
    UsageStore, decode_project, estimate_cost, model_family, project_label,
)


def _line(uuid, model="claude-opus-4-8", ts="2026-10-02T07:44:50.000Z",
          inp=10, out=20, cc=100, cr=200, thinking=5, session="s1",
          type_="assistant", with_usage=True):
    rec = {"type": type_, "uuid": uuid, "timestamp": ts, "sessionId": session,
           "message": {"model": model}}
    if with_usage:
        rec["message"]["usage"] = {
            "input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr,
            "output_tokens_details": {"thinking_tokens": thinking},
            "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 0},
        }
    return json.dumps(rec) + "\n"


def _write(dirpath, folder, lines):
    proj = dirpath / folder
    proj.mkdir(parents=True, exist_ok=True)
    f = proj / "session.jsonl"
    with f.open("w") as fh:
        fh.writelines(lines)
    return f


@pytest.fixture
def store(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    return UsageStore(db_path=tmp_path / "usage.db", projects_dir=projects), projects


# --- pure helpers -----------------------------------------------------------

def test_decode_and_label():
    assert decode_project("-Users-kevinyankam-dev-Jarvis") == "/Users/kevinyankam/dev/Jarvis"
    assert project_label("-Users-kevinyankam-dev-Jarvis") == "Jarvis"


def test_project_label_resolves_dashes_and_worktrees(tmp_path):
    home = tmp_path / "Users" / "me"
    (home / "dev" / "kanto-2026" / ".claude" / "worktrees" / "brave-x").mkdir(parents=True)
    (home / "Library" / "Application Support" / "Claude").mkdir(parents=True)
    label = lambda folder: project_label(folder, str(tmp_path), str(home))
    assert label("-Users-me-dev-kanto-2026") == "kanto-2026"
    assert label("-Users-me-dev-kanto-2026--claude-worktrees-brave-x") == "kanto-2026"
    assert label("-Users-me-Library-Application-Support-Claude") == "Claude"
    # A deleted project under a container folder keeps the last-segment guess.
    assert label("-Users-me-Documents-Astra") == "Astra"
    assert label("-Users-me-dev-gone-project") == "project"


def test_old_index_is_rebuilt_for_new_labels(store):
    import sqlite3

    s, projects = store
    _write(projects, "-Users-x-Jarvis", [_line("u1")])
    s.ingest()
    conn = sqlite3.connect(s.path)
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    fresh = UsageStore(db_path=s.path, projects_dir=projects)
    assert fresh.totals()["events"] == 0  # cleared, re-read on next ingest
    fresh.ingest()
    assert fresh.totals()["events"] == 1


def test_model_family():
    assert model_family("claude-opus-5-5") == "opus"
    assert model_family("claude-sonnet-5") == "sonnet"
    assert model_family("mystery") == "autre"


def test_estimate_cost_is_positive_and_family_scaled():
    tokens = {"input": 1_000_000, "output": 1_000_000, "cache_create": 0, "cache_read": 0}
    opus = estimate_cost(tokens, "claude-opus-4-8")
    sonnet = estimate_cost(tokens, "claude-sonnet-5")
    assert opus > sonnet > 0


# --- ingestion --------------------------------------------------------------

def test_ingest_counts_only_assistant_usage(store):
    s, projects = store
    _write(projects, "-tmp-proj", [
        _line("a"),
        _line("u", type_="user", with_usage=False),      # user turn: skipped
        _line("syn", model="<synthetic>"),               # synthetic: skipped
        "not json at all\n",                             # malformed: skipped
        _line("b"),
    ])
    result = s.ingest()
    assert result.new_events == 2
    assert result.files_read == 1


def test_ingest_is_incremental_and_dedups(store):
    s, projects = store
    f = _write(projects, "-tmp-proj", [_line("a"), _line("b")])
    assert s.ingest().new_events == 2
    # Nothing changed -> no re-read.
    second = s.ingest()
    assert second.new_events == 0 and second.files_read == 0
    # Append one line -> only the new one is ingested.
    with f.open("a") as fh:
        fh.write(_line("c"))
    third = s.ingest()
    assert third.new_events == 1 and third.files_read == 1
    assert s.totals()["events"] == 3


def test_partial_final_line_is_not_consumed_until_complete(store):
    s, projects = store
    proj = projects / "-tmp-proj"
    proj.mkdir(parents=True)
    f = proj / "session.jsonl"
    full = _line("a")
    with f.open("w") as fh:
        fh.write(full)
        fh.write(_line("b").rstrip("\n"))  # no trailing newline yet
    assert s.ingest().new_events == 1       # only the complete line
    with f.open("a") as fh:
        fh.write("\n")                       # the second line is now complete
    assert s.ingest().new_events == 1
    assert s.totals()["events"] == 2


# --- queries ----------------------------------------------------------------

def test_totals_sums_every_component(store):
    s, projects = store
    _write(projects, "-tmp-proj", [_line("a"), _line("b")])
    s.ingest()
    t = s.totals()
    assert t["input"] == 20 and t["output"] == 40
    assert t["cache_create"] == 200 and t["cache_read"] == 400
    assert t["thinking"] == 10 and t["web_search"] == 2
    assert t["total_tokens"] == 20 + 40 + 200 + 400
    assert t["sessions"] == 1


def test_by_model_and_cost(store):
    s, projects = store
    _write(projects, "-tmp-proj", [
        _line("a", model="claude-opus-4-8"),
        _line("b", model="claude-sonnet-5"),
    ])
    s.ingest()
    rows = s.by_model()
    by = {r["model"]: r for r in rows}
    assert set(by) == {"claude-opus-4-8", "claude-sonnet-5"}
    assert by["claude-opus-4-8"]["est_cost_usd"] > 0


def test_by_project_groups_by_label(store):
    s, projects = store
    _write(projects, "-Users-k-dev-Alpha", [_line("a")])
    _write(projects, "-Users-k-dev-Beta", [_line("b"), _line("c")])
    s.ingest()
    rows = {r["project"]: r for r in s.by_project()}
    assert rows["Alpha"]["events"] == 1
    assert rows["Beta"]["events"] == 2


def test_by_day_window(store):
    s, projects = store
    _write(projects, "-tmp-proj", [
        _line("a", ts="2026-10-01T10:00:00.000Z"),
        _line("b", ts="2026-10-02T10:00:00.000Z"),
    ])
    s.ingest()
    end = time.mktime(time.strptime("2026-10-02 23:00", "%Y-%m-%d %H:%M"))
    days = s.by_day(days=7, until=end)
    assert [d["day"] for d in days] == ["2026-10-01", "2026-10-02"]


def test_recent_sessions_aggregate_and_order(store):
    s, projects = store
    _write(projects, "-tmp-Alpha", [
        _line("a", ts="2026-10-01T10:00:00.000Z", session="s_old"),
        _line("b", ts="2026-10-05T10:00:00.000Z", session="s_new"),
        _line("c", ts="2026-10-05T10:05:00.000Z", session="s_new"),
    ])
    s.ingest()
    rows = s.recent_sessions(limit=10)
    assert [r["session"] for r in rows] == ["s_new", "s_old"]  # most recent first
    new = rows[0]
    assert new["events"] == 2 and new["project"] == "Alpha"
    assert new["est_cost_usd"] > 0 and new["total_tokens"] > 0


def test_recent_sessions_limit(store):
    s, projects = store
    _write(projects, "-tmp-Alpha", [
        _line(f"u{i}", ts=f"2026-10-0{i}T10:00:00.000Z", session=f"s{i}")
        for i in range(1, 5)
    ])
    s.ingest()
    assert len(s.recent_sessions(limit=2)) == 2


def test_clear_empties_index(store):
    s, projects = store
    f = _write(projects, "-tmp-proj", [_line("a")])
    s.ingest()
    s.clear()
    assert s.totals()["events"] == 0
    # After clear, the same file re-ingests (cursor was dropped too).
    assert s.ingest().new_events == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
