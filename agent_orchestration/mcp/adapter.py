"""Adapter that surfaces an MCP tool as a Jarvis ``BaseTool``.

This is the lowest-disruption integration point (Phase 1, Q3 option a): each MCP
tool is wrapped in a ``BaseTool`` so the existing planner, registry, risk-check,
approval and dispatch logic work unchanged. The MCP tool name is namespaced as
``<server>.<tool>`` to avoid collisions across servers and with built-in tools.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model

from agent_orchestration.exceptions import MCPConnectionError
from agent_orchestration.mcp import client
from agent_orchestration.mcp.config import MCPServerConfig
from agent_orchestration.models import ToolResult
from agent_orchestration.tools.base import BaseTool
from agent_orchestration.tools.risk import ToolRiskLevel

logger = logging.getLogger("jarvis.agent.mcp")

NAMESPACE_SEPARATOR = "."

_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _args_model_from_schema(
    model_name: str, input_schema: dict[str, Any]
) -> type[BaseModel]:
    """Build a Pydantic model from an MCP tool's JSON-Schema ``inputSchema``.

    Only top-level properties are typed; the model allows extra fields so that
    argument shapes we don't model exactly are still passed through to the server,
    which is the authoritative validator. Used by the graph's pre-execution
    validation step.
    """
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    fields: dict[str, Any] = {}
    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            json_type = (
                prop_schema.get("type") if isinstance(prop_schema, dict) else None
            )
            py_type = _JSON_TYPE_MAP.get(json_type, Any) if json_type else Any
            if prop_name in required:
                fields[prop_name] = (py_type, ...)
            else:
                fields[prop_name] = (py_type | None, None)

    return create_model(
        model_name,
        __config__=ConfigDict(extra="allow"),
        **fields,
    )


def _describe(description: str, input_schema: dict[str, Any]) -> str:
    """Append a compact argument summary so the planner's text-based prompt knows
    which arguments the tool accepts."""
    properties = input_schema.get("properties")
    if not properties:
        return description
    try:
        args_summary = json.dumps(properties, ensure_ascii=False)
    except (TypeError, ValueError):
        return description
    return f"{description}\nArguments (JSON Schema): {args_summary}"


class MCPTool(BaseTool):
    """A single MCP-server tool exposed through the Jarvis tool interface."""

    def __init__(
        self,
        server_name: str,
        server_config: MCPServerConfig,
        mcp_tool_name: str,
        description: str,
        input_schema: dict[str, Any],
    ) -> None:
        self.name = f"{server_name}{NAMESPACE_SEPARATOR}{mcp_tool_name}"
        self.description = _describe(description or "", input_schema)
        self.risk_level: ToolRiskLevel = server_config.risk_for(mcp_tool_name)
        self.args_schema = _args_model_from_schema(
            f"MCPArgs_{server_name}_{mcp_tool_name}", input_schema
        )
        self._server_config = server_config
        self._mcp_tool_name = mcp_tool_name

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = await client.call_tool(
                self._server_config, self._mcp_tool_name, arguments
            )
        except MCPConnectionError as exc:
            return ToolResult(
                tool_name=self.name,
                arguments=arguments,
                output="",
                success=False,
                error=str(exc),
            )

        output = client.render_tool_result(result)
        if result.isError:
            return ToolResult(
                tool_name=self.name,
                arguments=arguments,
                output="",
                success=False,
                error=output or "MCP tool reported an error.",
            )
        return ToolResult(
            tool_name=self.name,
            arguments=arguments,
            output=output,
            success=True,
        )
