"""Model Context Protocol client: lets Jarvis use external MCP servers."""
from jarvis.mcp.config import MCPConfigError, MCPServerSpec, default_mcp_config_path, load_mcp_config
from jarvis.mcp.hub import MCPHub

__all__ = [
    "MCPConfigError",
    "MCPHub",
    "MCPServerSpec",
    "default_mcp_config_path",
    "load_mcp_config",
]
