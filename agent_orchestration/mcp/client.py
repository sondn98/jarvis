"""Low-level MCP Streamable HTTP client helpers.

Each operation opens a fresh Streamable HTTP session, performs the MCP handshake,
runs the request, and tears the session down. Per-operation sessions keep the
client stateless (a natural fit for remote HTTP servers and for a process that may
serve many concurrent conversations) and make the client resilient to a server
that has restarted or dropped a previous connection.
"""

import logging
from datetime import timedelta

from mcp import ClientSession
from mcp import types as mcp_types
from mcp.client.streamable_http import streamablehttp_client

from agent_orchestration.exceptions import MCPConnectionError
from agent_orchestration.mcp.config import MCPServerConfig

logger = logging.getLogger("jarvis.agent.mcp")


async def list_tools(server: MCPServerConfig) -> list[mcp_types.Tool]:
    """Connect to ``server`` and return the tools it exposes.

    Raises MCPConnectionError if the server is unreachable or the handshake fails.
    """
    try:
        async with streamablehttp_client(
            url=server.url,
            headers=server.headers or None,
            timeout=timedelta(seconds=server.timeout),
        ) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return list(result.tools)
    except Exception as exc:  # noqa: BLE001 - normalize all transport/handshake errors
        raise MCPConnectionError(
            f"Failed to list tools from MCP server at {server.url}: {exc}"
        ) from exc


async def call_tool(
    server: MCPServerConfig, tool_name: str, arguments: dict[str, object]
) -> mcp_types.CallToolResult:
    """Invoke ``tool_name`` on ``server`` with ``arguments``.

    Returns the raw CallToolResult (the caller inspects ``isError`` / ``content``).
    Raises MCPConnectionError if the server is unreachable or the call transport
    fails.
    """
    try:
        async with streamablehttp_client(
            url=server.url,
            headers=server.headers or None,
            timeout=timedelta(seconds=server.timeout),
        ) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await session.call_tool(tool_name, arguments=arguments)
    except Exception as exc:  # noqa: BLE001 - normalize all transport/handshake errors
        raise MCPConnectionError(
            f"Failed to call tool '{tool_name}' on MCP server at {server.url}: {exc}"
        ) from exc


def render_tool_result(result: mcp_types.CallToolResult) -> str:
    """Flatten an MCP CallToolResult's content blocks into a single text string.

    The agent's tool-result model is text-based, so we concatenate text content and
    fall back to a JSON-ish repr for non-text blocks.
    """
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, mcp_types.TextContent):
            parts.append(block.text)
        else:
            parts.append(block.model_dump_json())
    return "\n".join(parts)
