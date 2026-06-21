import mcp.types as mcp_types

from agent_orchestration.exceptions import MCPConnectionError
from agent_orchestration.mcp import client as client_module
from agent_orchestration.mcp.config import MCPConfig, MCPServerConfig
from agent_orchestration.mcp.manager import MCPManager
from agent_orchestration.tools.registry import ToolRegistry


def _tool(name: str) -> mcp_types.Tool:
    return mcp_types.Tool(
        name=name,
        description=f"{name} description",
        inputSchema={"type": "object", "properties": {}},
    )


def _config(*names: str) -> MCPConfig:
    return MCPConfig(
        servers={name: MCPServerConfig(url=f"https://{name}/mcp") for name in names}
    )


async def test_ensure_ready_registers_namespaced_tools(monkeypatch):
    async def fake_list_tools(server):
        return [_tool("alpha"), _tool("beta")]

    monkeypatch.setattr(client_module, "list_tools", fake_list_tools)

    registry = ToolRegistry()
    manager = MCPManager(_config("svc"))
    await manager.ensure_ready(registry)

    names = {t.name for t in registry.list_tools()}
    assert names == {"svc.alpha", "svc.beta"}


async def test_unreachable_server_is_skipped(monkeypatch):
    async def fake_list_tools(server):
        if server.url == "https://good/mcp":
            return [_tool("ok")]
        raise MCPConnectionError("down")

    monkeypatch.setattr(client_module, "list_tools", fake_list_tools)

    registry = ToolRegistry()
    manager = MCPManager(_config("good", "bad"))
    await manager.ensure_ready(registry)

    names = {t.name for t in registry.list_tools()}
    assert names == {"good.ok"}


async def test_ensure_ready_is_idempotent(monkeypatch):
    calls = 0

    async def fake_list_tools(server):
        nonlocal calls
        calls += 1
        return [_tool("ok")]

    monkeypatch.setattr(client_module, "list_tools", fake_list_tools)

    registry = ToolRegistry()
    manager = MCPManager(_config("svc"))
    await manager.ensure_ready(registry)
    await manager.ensure_ready(registry)

    assert calls == 1
