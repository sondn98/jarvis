"""MCP (Model Context Protocol) client integration.

Jarvis acts as an MCP *client*: it connects to remote MCP servers over Streamable
HTTP and surfaces their tools to the agent orchestration loop via the existing
``ToolRegistry``. See ``agent_orchestration/mcp/manager.py`` for the entry point.
"""

from agent_orchestration.mcp.config import (
    MCPConfig,
    MCPServerConfig,
    load_mcp_config,
)
from agent_orchestration.mcp.manager import MCPManager

__all__ = ["MCPConfig", "MCPServerConfig", "MCPManager", "load_mcp_config"]
