import mcp.types as mcp_types
import pytest

from agent_orchestration.exceptions import MCPConnectionError
from agent_orchestration.mcp import adapter as adapter_module
from agent_orchestration.mcp.adapter import MCPTool
from agent_orchestration.mcp.config import MCPServerConfig
from agent_orchestration.tools.risk import ToolRiskLevel

_SERVER = MCPServerConfig(
    url="https://example.com/mcp",
    default_risk_level=ToolRiskLevel.EXTERNAL_WRITE,
    tool_risk_levels={"read_thing": "safe_read_only"},
)

_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
    "required": ["query"],
}


def _make_tool(mcp_name: str = "send_thing") -> MCPTool:
    return MCPTool(
        server_name="gmail",
        server_config=_SERVER,
        mcp_tool_name=mcp_name,
        description="Send a thing.",
        input_schema=_SCHEMA,
    )


def test_name_is_namespaced():
    assert _make_tool().name == "gmail.send_thing"


def test_risk_level_from_config():
    assert _make_tool("send_thing").risk_level is ToolRiskLevel.EXTERNAL_WRITE
    assert _make_tool("read_thing").risk_level is ToolRiskLevel.SAFE_READ_ONLY


def test_args_schema_validates_required():
    tool = _make_tool()
    # Required field present -> ok.
    tool.args_schema(query="hello")
    # Missing required field -> error.
    with pytest.raises(Exception):
        tool.args_schema(limit=5)


def test_description_includes_schema():
    assert "query" in _make_tool().description


async def test_arun_success(monkeypatch):
    async def fake_call_tool(server, name, arguments):
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="result text")],
            isError=False,
        )

    monkeypatch.setattr(adapter_module.client, "call_tool", fake_call_tool)
    result = await _make_tool().arun({"query": "hi"})
    assert result.success is True
    assert result.output == "result text"


async def test_arun_tool_error(monkeypatch):
    async def fake_call_tool(server, name, arguments):
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="boom")],
            isError=True,
        )

    monkeypatch.setattr(adapter_module.client, "call_tool", fake_call_tool)
    result = await _make_tool().arun({"query": "hi"})
    assert result.success is False
    assert "boom" in (result.error or "")


async def test_arun_connection_error(monkeypatch):
    async def fake_call_tool(server, name, arguments):
        raise MCPConnectionError("unreachable")

    monkeypatch.setattr(adapter_module.client, "call_tool", fake_call_tool)
    result = await _make_tool().arun({"query": "hi"})
    assert result.success is False
    assert "unreachable" in (result.error or "")
