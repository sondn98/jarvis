"""Manual connectivity smoke check for the MCP client (Phase 2, step 2.1).

Connects to a single MCP server over Streamable HTTP and lists its tools, proving
end-to-end connectivity before the rest of the integration is exercised.

Usage:
    # Point at any reachable Streamable HTTP MCP server:
    MCP_TEST_URL="https://your-server/mcp" \
    MCP_TEST_AUTH="Bearer <token>" \
        uv run python scripts/manual_mcp_check.py

If MCP_TEST_AUTH is set it is sent as the Authorization header.
"""

import asyncio
import os

from agent_orchestration.mcp import client
from agent_orchestration.mcp.config import MCPServerConfig


async def main() -> None:
    url = os.environ.get("MCP_TEST_URL")
    if not url:
        raise SystemExit("Set MCP_TEST_URL to a reachable Streamable HTTP MCP server.")

    headers: dict[str, str] = {}
    auth = os.environ.get("MCP_TEST_AUTH")
    if auth:
        headers["Authorization"] = auth

    server = MCPServerConfig(url=url, headers=headers)

    print(f"Connecting to {url} ...")
    tools = await client.list_tools(server)
    print(f"Connected. {len(tools)} tool(s) discovered:\n")
    for tool in tools:
        print(f"- {tool.name}: {tool.description or '(no description)'}")


if __name__ == "__main__":
    asyncio.run(main())
