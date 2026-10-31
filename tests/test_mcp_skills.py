import asyncio
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.capabilities.results import ToolResult
from jarvis.live.registry import SAFE_MODE_ALLOWED, create_live_registry
from jarvis.mcp import MCPConfigError, MCPHub, MCPServerSpec, load_mcp_config
from jarvis.skills import SkillLibrary, parse_skill


# --- configuration -------------------------------------------------------

def _write(path: Path, data) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_missing_config_means_no_server(tmp_path):
    assert load_mcp_config(tmp_path / "absent.json") == {}


def test_claude_desktop_block_is_accepted_and_disabled_skipped(tmp_path):
    path = _write(tmp_path / "mcp.json", {"mcpServers": {
        "github": {"command": "npx", "args": ["-y", "server-github"], "env": {"TOKEN": "x"},
                   "autoApprove": ["search_issues"]},
        "remote": {"url": "https://example.test/mcp", "timeout": 999},
        "off": {"command": "x", "disabled": True},
    }})
    specs = load_mcp_config(path)
    assert sorted(specs) == ["github", "remote"]
    assert specs["github"].args == ("-y", "server-github")
    assert specs["github"].auto_approve == frozenset({"search_issues"})
    assert specs["remote"].transport == "http"
    assert specs["remote"].timeout == 300.0


@pytest.mark.parametrize("server", [
    {},
    {"command": "a", "url": "https://b"},
    {"url": "ftp://b"},
    {"command": "a", "args": "not-a-list"},
    {"command": "a", "autoApprove": "all"},
    {"command": "a", "timeout": 0},
])
def test_invalid_server_entries_are_rejected(tmp_path, server):
    path = _write(tmp_path / "mcp.json", {"mcpServers": {"s": server}})
    with pytest.raises(MCPConfigError):
        load_mcp_config(path)


def test_invalid_json_is_a_clear_error(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(MCPConfigError, match="JSON"):
        load_mcp_config(path)


# --- hub -----------------------------------------------------------------

class FakeSession:
    def __init__(self, fail_call=False, hang=False):
        self.calls = []
        self.fail_call = fail_call
        self.hang = hang
        self.tools = [
            SimpleNamespace(name="search", description="Cherche", annotations=SimpleNamespace(readOnlyHint=True),
                            inputSchema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}),
            SimpleNamespace(name="create_issue", description="Cree un ticket", annotations=None,
                            inputSchema={"type": "object", "properties": {"title": {"type": "string"}}}),
        ]

    async def list_tools(self):
        return SimpleNamespace(tools=self.tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.hang:
            await asyncio.sleep(10)
        if self.fail_call:
            raise RuntimeError("boom")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=f"{name}:{arguments}")],
                               isError=False, structuredContent=None)


class FakeOpener:
    def __init__(self, session=None, error=None):
        self.session = session or FakeSession()
        self.error = error
        self.opened = 0
        self.closed = 0

    def __call__(self, spec):
        opener = self

        @contextlib.asynccontextmanager
        async def cm():
            opener.opened += 1
            if opener.error:
                raise opener.error
            try:
                yield opener.session
            finally:
                opener.closed += 1
        return cm()


def _hub(opener, **spec):
    specs = {"gh": MCPServerSpec(name="gh", command="fake", **spec)}
    return MCPHub(config_loader=lambda: specs, opener=opener)


def test_list_tools_summarizes_schema_and_connects_once():
    opener = FakeOpener()
    hub = _hub(opener, auto_approve=frozenset({"search"}))

    async def run():
        first = await hub.list_tools()
        await hub.list_tools("gh")
        await hub.aclose()
        return first

    result = asyncio.run(run())
    assert result.ok
    tools = {t["name"]: t for t in result.data["servers"][0]["tools"]}
    assert tools["search"]["required"] == ["q"]
    assert tools["search"]["read_only_hint"] is True
    assert tools["search"]["auto_approved"] is True
    assert tools["create_issue"]["auto_approved"] is False
    assert opener.opened == 1 and opener.closed == 1


def test_unreachable_server_is_reported_not_raised():
    hub = _hub(FakeOpener(error=FileNotFoundError()))
    result = asyncio.run(hub.list_tools())
    assert result.ok
    assert result.data["servers"][0] == {"server": "gh", "ok": False, "error": "commande introuvable"}


def test_call_validates_tool_and_required_arguments():
    opener = FakeOpener()
    hub = _hub(opener)

    async def run():
        unknown = await hub.call_tool("gh", "nope", {})
        missing = await hub.call_tool("gh", "search", {})
        server = await hub.call_tool("other", "search", {"q": "x"})
        ok = await hub.call_tool("gh", "search", {"q": "x"})
        await hub.aclose()
        return unknown, missing, server, ok

    unknown, missing, server, ok = asyncio.run(run())
    assert unknown.error_code == "mcp_unknown_tool"
    assert missing.error_code == "mcp_missing_arguments"
    assert server.error_code == "mcp_unknown_server"
    assert ok.ok and ok.data["output"] == "search:{'q': 'x'}"
    assert opener.session.calls == [("search", {"q": "x"})]


def test_failed_call_drops_the_connection_so_the_next_one_reconnects():
    opener = FakeOpener(session=FakeSession(fail_call=True))
    hub = _hub(opener)

    async def run():
        failed = await hub.call_tool("gh", "search", {"q": "x"})
        opener.session.fail_call = False
        again = await hub.call_tool("gh", "search", {"q": "x"})
        await hub.aclose()
        return failed, again

    failed, again = asyncio.run(run())
    assert failed.error_code == "mcp_call_failed"
    assert again.ok
    assert opener.opened == 2


def test_call_timeout_says_effect_is_unknown():
    hub = _hub(FakeOpener(session=FakeSession(hang=True)), timeout=0.05)

    async def run():
        result = await hub.call_tool("gh", "search", {"q": "x"})
        await hub.aclose()
        return result

    result = asyncio.run(run())
    assert result.error_code == "mcp_timeout"
    assert "inconnu" in result.message


def test_long_output_is_truncated_and_flagged():
    session = FakeSession()

    async def big(name, arguments):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="x" * 10000)],
                               isError=False, structuredContent=None)
    session.call_tool = big
    hub = _hub(FakeOpener(session=session))

    async def run():
        result = await hub.call_tool("gh", "search", {"q": "x"})
        await hub.aclose()
        return result

    result = asyncio.run(run())
    assert result.data["truncated"] is True
    assert len(result.data["output"]) == 4000


def test_invalid_config_is_surfaced_by_list():
    def broken():
        raise MCPConfigError("mcp.json n'est pas du JSON valide (ligne 1).")
    hub = MCPHub(config_loader=broken, opener=FakeOpener())
    result = asyncio.run(hub.list_tools())
    assert not result.ok
    assert result.error_code == "mcp_config_invalid"


# --- skills --------------------------------------------------------------

def _skill(root: Path, folder: str, text: str) -> Path:
    directory = root / folder
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return directory


SKILL = """---
name: weekly-review
description: >
  Fait la revue hebdomadaire
  des taches.
---
# Revue
1. Liste les rappels.
"""


def test_library_lists_and_loads_instructions(tmp_path):
    folder = _skill(tmp_path, "weekly", SKILL)
    (folder / "reference.md").write_text("Details", encoding="utf-8")
    (folder / "run.sh").write_text("rm -rf /", encoding="utf-8")
    library = SkillLibrary([tmp_path])

    listed = library.list_skills()
    assert listed.data["skills"] == [{"name": "weekly-review", "description": "Fait la revue hebdomadaire des taches."}]

    used = library.use_skill("weekly-review")
    assert used.ok
    assert used.data["instructions"].startswith("# Revue")
    assert used.data["files"] == ["reference.md", "run.sh"]

    reference = library.use_skill("weekly-review", "reference.md")
    assert reference.data["content"] == "Details"
    script = library.use_skill("weekly-review", "run.sh")
    assert script.error_code == "skill_file_not_text"


def test_skill_file_cannot_escape_its_folder(tmp_path):
    _skill(tmp_path, "weekly", SKILL)
    (tmp_path / "secret.md").write_text("secret", encoding="utf-8")
    result = SkillLibrary([tmp_path]).use_skill("weekly-review", "../secret.md")
    assert result.error_code == "skill_file_not_found"


@pytest.mark.parametrize("text", [
    "no front matter",
    "---\nname: Bad Name\ndescription: x\n---\n",
    "---\nname: ok\n---\n",
    "---\nname: [unclosed\n---\n",
])
def test_invalid_skills_are_ignored(tmp_path, text):
    _skill(tmp_path, "s", text)
    assert parse_skill(tmp_path / "s" / "SKILL.md") is None
    assert SkillLibrary([tmp_path]).skills() == {}


def test_unknown_skill_lists_what_exists(tmp_path):
    _skill(tmp_path, "weekly", SKILL)
    result = SkillLibrary([tmp_path]).use_skill("missing")
    assert result.error_code == "skill_not_found"
    assert "weekly-review" in result.message


# --- voice tools ---------------------------------------------------------

class FakeMemory:
    def log_action(self, *a, **k):
        return None


def _registry(tmp_path, opener, auto_approve=frozenset()):
    registry = create_live_registry(memory_capability=FakeMemory())
    specs = {"gh": MCPServerSpec(name="gh", command="fake", auto_approve=auto_approve)}
    registry.mcp_hub = MCPHub(config_loader=lambda: specs, opener=opener)
    _skill(tmp_path, "weekly", SKILL)
    registry.skill_library = SkillLibrary([tmp_path])
    tools = {tool.info.name: tool for tool in registry.livekit_tools()}
    return registry, tools


def test_extension_tools_are_registered_and_safe_mode_classified(tmp_path):
    _, tools = _registry(tmp_path, FakeOpener())
    for name in ("list_mcp_tools", "call_mcp_tool", "list_skills", "use_skill"):
        assert name in tools
    assert {"list_mcp_tools", "list_skills", "use_skill"} <= SAFE_MODE_ALLOWED
    assert "call_mcp_tool" not in SAFE_MODE_ALLOWED
    assert "weekly-review" in tools["use_skill"].info.description


def test_unapproved_call_waits_for_confirmation(tmp_path):
    opener = FakeOpener()
    registry, tools = _registry(tmp_path, opener)

    async def run():
        prepared = await tools["call_mcp_tool"]("gh", "create_issue", '{"title": "Bug"}')
        assert opener.session.calls == []
        confirmed = await tools["confirm_action"](prepared["token"])
        await registry.aclose()
        return prepared, confirmed

    prepared, confirmed = asyncio.run(run())
    assert prepared["requires_confirmation"] is True
    assert confirmed["ok"] is True
    assert opener.session.calls == [("create_issue", {"title": "Bug"})]


def test_cancelled_call_never_runs(tmp_path):
    opener = FakeOpener()
    registry, tools = _registry(tmp_path, opener)

    async def run():
        prepared = await tools["call_mcp_tool"]("gh", "create_issue", "{}")
        await tools["cancel_action"](prepared["token"])
        await registry.aclose()

    asyncio.run(run())
    assert opener.session.calls == []


def test_auto_approved_call_runs_directly(tmp_path):
    opener = FakeOpener()
    registry, tools = _registry(tmp_path, opener, auto_approve=frozenset({"search"}))

    async def run():
        result = await tools["call_mcp_tool"]("gh", "search", '{"q": "jarvis"}')
        await registry.aclose()
        return result

    result = asyncio.run(run())
    assert result["ok"] is True
    assert "requires_confirmation" not in result
    assert opener.session.calls == [("search", {"q": "jarvis"})]


@pytest.mark.parametrize("arguments", ["not json", "[1, 2]"])
def test_bad_arguments_are_refused_before_any_connection(tmp_path, arguments):
    opener = FakeOpener()
    _, tools = _registry(tmp_path, opener)
    result = asyncio.run(tools["call_mcp_tool"]("gh", "search", arguments))
    assert result["error_code"] == "mcp_invalid_arguments"
    assert opener.opened == 0


def test_safe_mode_blocks_mcp_calls_but_not_listing(tmp_path):
    opener = FakeOpener()
    registry, tools = _registry(tmp_path, opener, auto_approve=frozenset({"search"}))
    registry.read_only_mode = True

    async def run():
        blocked = await tools["call_mcp_tool"]("gh", "search", '{"q": "x"}')
        listed = await tools["list_mcp_tools"]()
        skill = await tools["use_skill"]("weekly-review")
        await registry.aclose()
        return blocked, listed, skill

    blocked, listed, skill = asyncio.run(run())
    assert blocked["error_code"] == "read_only_mode"
    assert opener.session.calls == []
    assert listed["ok"] and skill["ok"]
