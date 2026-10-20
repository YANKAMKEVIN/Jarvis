import json
import subprocess
import types

import pytest

from jarvis.capabilities.claude_sessions import ClaudeSessionsCapability
from jarvis.tools.claude_cli import ClaudeCli, ClaudeCliError


def _completed(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# --- ClaudeCli (tool) -------------------------------------------------------

def test_run_once_parses_json():
    payload = {"result": "  Bonjour  ", "is_error": False, "num_turns": 2,
               "session_id": "abc", "total_cost_usd": 0.01,
               "usage": {"output_tokens": 42}}
    calls = {}

    def runner(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        return _completed(0, json.dumps(payload))

    cli = ClaudeCli(binary="claude", runner=runner)
    out = cli.run_once("fais X", cwd="/tmp")
    assert out["result"] == "Bonjour" and out["num_turns"] == 2
    assert out["session_id"] == "abc" and out["output_tokens"] == 42
    assert calls["cmd"] == ["claude", "-p", "fais X", "--output-format", "json"]
    assert calls["cwd"] == "/tmp"


def test_run_once_timeout():
    def runner(cmd, **k):
        raise subprocess.TimeoutExpired(cmd, 1)

    with pytest.raises(ClaudeCliError) as exc:
        ClaudeCli(binary="claude", runner=runner).run_once("x")
    assert exc.value.code == "timeout"


def test_run_once_nonzero_returncode():
    def runner(cmd, **k):
        return _completed(1, "", "boom\nlast line")
    with pytest.raises(ClaudeCliError) as exc:
        ClaudeCli(binary="claude", runner=runner).run_once("x")
    assert exc.value.code == "claude_failed" and "last line" in exc.value.message


def test_run_once_missing_binary():
    cli = ClaudeCli(binary=None)
    cli.resolve = lambda: None
    with pytest.raises(ClaudeCliError) as exc:
        cli.run_once("x")
    assert exc.value.code == "claude_missing"


def test_open_interactive_builds_terminal_script():
    captured = {}

    def opener(cmd, **k):
        captured["cmd"] = cmd
        return _completed(0)

    cli = ClaudeCli(binary="claude", opener=opener)
    cli.open_interactive(cwd="/Users/me/My Project")
    script = captured["cmd"][2]
    assert captured["cmd"][0] == "osascript"
    assert "Terminal" in script and "activate" in script
    assert "claude" in script and "'/Users/me/My Project'" in script  # shell-quoted cwd


# --- capability -------------------------------------------------------------

class FakeCli:
    def __init__(self, avail=True, out=None, raises=None):
        self._avail = avail
        self._out = out or {"result": "ok", "is_error": False, "num_turns": 1,
                            "session_id": "s", "cost_usd": 0.0, "output_tokens": 3}
        self._raises = raises
        self.run_calls = []
        self.opened = None

    def available(self):
        return self._avail

    def run_once(self, prompt, cwd=None, timeout=300):
        self.run_calls.append((prompt, cwd))
        if self._raises:
            raise self._raises
        return self._out

    def open_interactive(self, cwd=None):
        if self._raises:
            raise self._raises
        self.opened = cwd


def test_run_task_success(tmp_path):
    cli = FakeCli(out={"result": "Fait.", "is_error": False, "num_turns": 3,
                       "session_id": "x", "cost_usd": 0.2, "output_tokens": 10})
    cap = ClaudeSessionsCapability(cli=cli, default_dir=str(tmp_path))
    r = cap.run_task("range mes fichiers")
    assert r.ok and "Fait." in r.message and r.data["result"] == "Fait."
    assert cli.run_calls[0][1] == str(tmp_path)  # ran in default dir


def test_run_task_rejects_empty_prompt(tmp_path):
    cap = ClaudeSessionsCapability(cli=FakeCli(), default_dir=str(tmp_path))
    r = cap.run_task("   ")
    assert not r.ok and r.error_code == "invalid_prompt"


def test_run_task_reports_claude_error(tmp_path):
    cli = FakeCli(out={"result": "nope", "is_error": True, "num_turns": 1,
                       "session_id": "x", "cost_usd": 0.0, "output_tokens": 0})
    cap = ClaudeSessionsCapability(cli=cli, default_dir=str(tmp_path))
    r = cap.run_task("x")
    assert not r.ok and r.error_code == "claude_error"


def test_run_task_unavailable(tmp_path):
    cap = ClaudeSessionsCapability(cli=FakeCli(avail=False), default_dir=str(tmp_path))
    r = cap.run_task("x")
    assert not r.ok and r.error_code == "claude_missing"


def test_run_task_uses_named_directory(tmp_path):
    cap = ClaudeSessionsCapability(cli=(cli := FakeCli()), default_dir="/nope")
    cap.run_task("x", directory=str(tmp_path))
    assert cli.run_calls[0][1] == str(tmp_path)


def test_run_task_falls_back_when_directory_missing(tmp_path):
    cap = ClaudeSessionsCapability(cli=(cli := FakeCli()), default_dir=str(tmp_path))
    cap.run_task("x", directory="/does/not/exist")
    assert cli.run_calls[0][1] == str(tmp_path)


def test_open_session_success(tmp_path):
    cap = ClaudeSessionsCapability(cli=(cli := FakeCli()), default_dir=str(tmp_path))
    r = cap.open_session()
    assert r.ok and cli.opened == str(tmp_path)


def test_open_session_failure(tmp_path):
    cli = FakeCli(raises=ClaudeCliError("boom", "open_failed"))
    cap = ClaudeSessionsCapability(cli=cli, default_dir=str(tmp_path))
    r = cap.open_session()
    assert not r.ok and r.error_code == "open_failed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
