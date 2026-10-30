"""MCP server configuration, in the Claude Desktop `mcpServers` format.

The file lives at ~/Library/Application Support/Jarvis/mcp.json (override with
JARVIS_MCP_CONFIG), so a block copied from claude_desktop_config.json works
as is. Jarvis-specific keys per server:

- "autoApprove": tool names that may run without a spoken confirmation. Every
  other tool goes through the prepare -> confirm_action flow.
- "disabled": true keeps the entry without ever starting the server.
- "timeout": seconds allowed for one tool call (default 30, max 300).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CALL_TIMEOUT = 30.0
MAX_CALL_TIMEOUT = 300.0
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class MCPConfigError(Exception):
    pass


@dataclass(frozen=True)
class MCPServerSpec:
    name: str
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    auto_approve: frozenset[str] = frozenset()
    timeout: float = DEFAULT_CALL_TIMEOUT

    @property
    def transport(self) -> str:
        return "http" if self.url else "stdio"


def default_mcp_config_path() -> Path:
    override = os.environ.get("JARVIS_MCP_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Jarvis" / "mcp.json"


def _string_map(value, label: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise MCPConfigError(f"{label} doit etre un objet de chaines.")
    return dict(value)


def _parse_server(name: str, raw) -> MCPServerSpec | None:
    if not isinstance(name, str) or not _NAME.match(name):
        raise MCPConfigError(f"Nom de serveur MCP invalide : {name!r}.")
    if not isinstance(raw, dict):
        raise MCPConfigError(f"Le serveur {name} doit etre un objet.")
    if raw.get("disabled") is True:
        return None
    command, url = raw.get("command"), raw.get("url")
    if bool(command) == bool(url):
        raise MCPConfigError(f"Le serveur {name} doit definir soit command, soit url.")
    if command is not None and not isinstance(command, str):
        raise MCPConfigError(f"command du serveur {name} doit etre une chaine.")
    if url is not None and (not isinstance(url, str) or not url.startswith(("http://", "https://"))):
        raise MCPConfigError(f"url du serveur {name} doit commencer par http:// ou https://.")
    args = raw.get("args", [])
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise MCPConfigError(f"args du serveur {name} doit etre une liste de chaines.")
    approve = raw.get("autoApprove", [])
    if not isinstance(approve, list) or not all(isinstance(a, str) for a in approve):
        raise MCPConfigError(f"autoApprove du serveur {name} doit etre une liste de noms d'outils.")
    timeout = raw.get("timeout", DEFAULT_CALL_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise MCPConfigError(f"timeout du serveur {name} doit etre un nombre positif.")
    return MCPServerSpec(
        name=name,
        command=command,
        args=tuple(args),
        env=_string_map(raw.get("env"), f"env du serveur {name}"),
        url=url,
        headers=_string_map(raw.get("headers"), f"headers du serveur {name}"),
        auto_approve=frozenset(approve),
        timeout=min(float(timeout), MAX_CALL_TIMEOUT),
    )


def load_mcp_config(path: Path | None = None) -> dict[str, MCPServerSpec]:
    """Return the enabled servers by name; a missing file means no server."""
    path = path or default_mcp_config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise MCPConfigError(f"Lecture impossible de {path.name} : {error.strerror}.") from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise MCPConfigError(f"{path.name} n'est pas du JSON valide (ligne {error.lineno}).") from error
    servers = data.get("mcpServers", {}) if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        raise MCPConfigError(f"{path.name} doit contenir un objet mcpServers.")
    specs = {}
    for name, raw in servers.items():
        spec = _parse_server(name, raw)
        if spec is not None:
            specs[name] = spec
    return specs
