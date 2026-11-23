"""Settings editor for mcp.json (idea 31)."""
import contextlib
import json
import os
import stat
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from jarvis.mcp import editor
from jarvis.mcp.config import MCPConfigError, load_mcp_config

CONFIG = {
    "mcpServers": {
        "github": {"command": "npx", "args": ["-y", "server-github"],
                   "env": {"GITHUB_TOKEN": "SECRET_TOKEN_VALUE"}, "autoApprove": ["get_issue"]},
        "maison": {"url": "https://ha.local/mcp", "headers": {"Authorization": "Bearer SECRET"}, "disabled": True},
    },
    "otherKey": {"kept": True},
}


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(CONFIG))
    return path


def test_rows_never_carry_secret_values(config):
    rows = editor.server_rows(editor.read_raw_config(config))
    assert [row["name"] for row in rows] == ["github", "maison"]
    assert rows[0]["secret_keys"] == ["GITHUB_TOKEN"] and rows[1]["disabled"] is True
    assert "SECRET" not in json.dumps(rows)


def test_edits_are_validated_saved_atomically_and_private(config):
    raw = editor.read_raw_config(config)
    editor.set_auto_approve(raw, "github", ["search_issues", "get_issue"])
    editor.set_disabled(raw, "maison", False)
    editor.add_server(raw, "notes", "uvx 'mon serveur' --lecture")
    editor.save_raw_config(raw, config)
    saved = json.loads(config.read_text())
    assert saved["otherKey"] == {"kept": True}
    assert saved["mcpServers"]["github"]["env"] == {"GITHUB_TOKEN": "SECRET_TOKEN_VALUE"}
    assert saved["mcpServers"]["notes"] == {"command": "uvx", "args": ["mon serveur", "--lecture"]}
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    specs = load_mcp_config(config)
    assert specs["github"].auto_approve == {"search_issues", "get_issue"} and "maison" in specs


def test_invalid_entries_are_refused_before_writing(config):
    raw = editor.read_raw_config(config)
    with pytest.raises(MCPConfigError):
        editor.add_server(raw, "bad name!", "npx x")
    with pytest.raises(MCPConfigError):
        editor.add_server(raw, "github", "npx x")
    with pytest.raises(MCPConfigError):
        editor.add_server(raw, "vide", "   ")
    raw["mcpServers"]["github"]["timeout"] = -1
    before = config.read_text()
    with pytest.raises(MCPConfigError):
        editor.save_raw_config(raw, config)
    assert config.read_text() == before


class Session:
    async def list_tools(self):
        return NS(tools=[NS(name="get_issue", description="", inputSchema={}), NS(name="create_issue", description="", inputSchema={})])


@contextlib.asynccontextmanager
async def opener(spec):
    yield Session()


def test_probe_lists_tools_even_for_a_disabled_server(config):
    result = editor.probe_server(editor.read_raw_config(config), "github", opener)
    assert result == {"ok": True, "error": "", "tools": ["get_issue", "create_issue"]}


def test_dialog_tests_checks_and_saves(config):
    QApplication.instance() or QApplication([])
    from jarvis.desktop.mcp_dialog import MCPDialog
    dialog = MCPDialog(path=config, opener=opener, threaded=False)
    try:
        assert dialog.servers.count() == 2 and dialog.current() == "github"
        assert "SECRET" not in dialog.detail.text() and "GITHUB_TOKEN" in dialog.detail.text()
        dialog.test()
        assert "joignable" in dialog.status.text()
        tools = {dialog.tools.item(i).text(): dialog.tools.item(i) for i in range(dialog.tools.count())}
        assert set(tools) == {"get_issue", "create_issue"}
        assert tools["get_issue"].checkState() == Qt.CheckState.Checked
        tools["create_issue"].setCheckState(Qt.CheckState.Checked)
        dialog.new_name.setText("web");dialog.new_target.setText("https://example.org/mcp");dialog.add()
        assert dialog.current() == "web"
        assert dialog.save()
        saved = json.loads(config.read_text())["mcpServers"]
        assert saved["github"]["autoApprove"] == ["create_issue", "get_issue"]
        assert saved["web"] == {"url": "https://example.org/mcp"}
    finally:
        dialog.close()


def test_dialog_reports_an_unreadable_file(tmp_path):
    QApplication.instance() or QApplication([])
    from jarvis.desktop.mcp_dialog import MCPDialog
    path = tmp_path / "mcp.json"
    path.write_text("{oops")
    dialog = MCPDialog(path=path, threaded=False)
    try:
        assert "invalide" in dialog.status.text() and dialog.servers.count() == 0
        assert dialog.save() is False and path.read_text() == "{oops"
    finally:
        dialog.close()
