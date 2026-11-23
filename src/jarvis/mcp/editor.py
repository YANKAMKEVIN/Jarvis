"""Edit mcp.json without hand-written JSON (Settings > Serveurs MCP).

The raw file is kept as is (unknown keys, env and headers included) and only
the edited keys change. Every save is validated with the same parser Jarvis
uses at runtime, and written atomically, owner-only (it may hold tokens).
Secrets (env, headers) are never shown: rows only carry their key names.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any

from jarvis.mcp.config import MCPConfigError, _parse_server, default_mcp_config_path


def read_raw_config(path: Path | None = None) -> dict[str, Any]:
    path = path or default_mcp_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"mcpServers": {}}
    except (OSError, json.JSONDecodeError) as error:
        raise MCPConfigError(f"{path.name} illisible : {error}") from error
    if not isinstance(data, dict) or not isinstance(data.setdefault("mcpServers", {}), dict):
        raise MCPConfigError(f"{path.name} doit contenir un objet mcpServers.")
    return data


def server_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, server in sorted(raw.get("mcpServers", {}).items()):
        server = server if isinstance(server, dict) else {}
        rows.append({
            "name": name,
            "transport": "http" if server.get("url") else "stdio",
            "target": server.get("url") or " ".join([server.get("command") or "", *server.get("args", [])]).strip(),
            "disabled": server.get("disabled") is True,
            "auto_approve": sorted(server.get("autoApprove", [])),
            "secret_keys": sorted(list(server.get("env", {}) or {}) + list(server.get("headers", {}) or {})),
        })
    return rows


def validate(raw: dict[str, Any]) -> None:
    for name, server in raw.get("mcpServers", {}).items():
        _parse_server(name, server)


def add_server(raw: dict[str, Any], name: str, target: str) -> None:
    """`target` is an http(s) URL or a command line (« npx -y server »)."""
    servers = raw.setdefault("mcpServers", {})
    name = (name or "").strip()
    if name in servers:
        raise MCPConfigError(f"Un serveur s'appelle deja {name}.")
    target = (target or "").strip()
    if target.startswith(("http://", "https://")):
        entry: dict[str, Any] = {"url": target}
    else:
        try:
            parts = shlex.split(target)
        except ValueError as error:
            raise MCPConfigError(f"Commande illisible : {error}.") from error
        if not parts:
            raise MCPConfigError("Indiquez une commande ou une URL.")
        entry = {"command": parts[0], "args": parts[1:]}
    _parse_server(name, entry)
    servers[name] = entry


def remove_server(raw: dict[str, Any], name: str) -> None:
    raw.get("mcpServers", {}).pop(name, None)


def set_disabled(raw: dict[str, Any], name: str, disabled: bool) -> None:
    server = raw["mcpServers"][name]
    if disabled:
        server["disabled"] = True
    else:
        server.pop("disabled", None)


def set_auto_approve(raw: dict[str, Any], name: str, tools) -> None:
    tools = sorted({str(tool) for tool in tools})
    server = raw["mcpServers"][name]
    if tools:
        server["autoApprove"] = tools
    else:
        server.pop("autoApprove", None)


def save_raw_config(raw: dict[str, Any], path: Path | None = None) -> Path:
    validate(raw)
    path = path or default_mcp_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".mcp-", suffix=".json")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(raw, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return path


def probe_server(raw: dict[str, Any], name: str, opener=None) -> dict[str, Any]:
    """Connect to one server (even disabled) and list its tools, then close."""
    from jarvis.mcp.hub import MCPHub, open_sdk_session

    server = dict(raw["mcpServers"][name])
    server.pop("disabled", None)
    spec = _parse_server(name, server)
    hub = MCPHub(config_loader=lambda: {name: spec}, opener=opener or open_sdk_session)

    async def run():
        try:
            return await hub.list_tools(name)
        finally:
            await hub.aclose()

    result = asyncio.run(run())
    entry = (result.data.get("servers") or [{}])[0]
    return {"ok": bool(entry.get("ok")), "error": entry.get("error", ""),
            "tools": [tool["name"] for tool in entry.get("tools", [])]}
