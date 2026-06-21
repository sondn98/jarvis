"""Lazy discovery and registration of MCP tools.

Connection lifecycle (Phase 1, Q5): the config file is parsed at startup, but MCP
servers are *not* contacted until the first agent request. ``ensure_ready`` runs
discovery exactly once (cached for the process lifetime), connecting to every
configured server, listing its tools, and registering each as an ``MCPTool`` in the
shared ``ToolRegistry``. A server that is unreachable or fails to initialize is
skipped with a warning so one bad server cannot take down the agent.
"""

import asyncio
import logging

from agent_orchestration.exceptions import MCPConnectionError
from agent_orchestration.mcp.adapter import MCPTool
from agent_orchestration.mcp.config import MCPConfig, MCPServerConfig
from agent_orchestration.tools.registry import ToolRegistry

logger = logging.getLogger("jarvis.agent.mcp")


class MCPManager:
    """Owns the configured MCP servers and registers their tools on first use."""

    def __init__(self, config: MCPConfig) -> None:
        self._config = config
        self._ready = False
        self._lock = asyncio.Lock()

    @property
    def server_count(self) -> int:
        return len(self._config.servers)

    async def ensure_ready(self, registry: ToolRegistry) -> None:
        """Discover and register MCP tools, exactly once.

        Idempotent and safe under concurrent first requests (guarded by a lock).
        Never raises for an individual server failure — unreachable servers are
        logged and skipped.
        """
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            for server_name, server_config in self._config.servers.items():
                await self._register_server(server_name, server_config, registry)
            self._ready = True

    async def _register_server(
        self,
        server_name: str,
        server_config: MCPServerConfig,
        registry: ToolRegistry,
    ) -> None:
        from agent_orchestration.mcp import client

        try:
            tools = await client.list_tools(server_config)
        except MCPConnectionError as exc:
            logger.warning("Skipping MCP server '%s': %s", server_name, exc)
            return

        for tool in tools:
            adapter = MCPTool(
                server_name=server_name,
                server_config=server_config,
                mcp_tool_name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
            )
            registry.register(adapter)
            logger.info(
                "Registered MCP tool '%s' (risk=%s) from server '%s'",
                adapter.name,
                adapter.risk_level.value,
                server_name,
            )
