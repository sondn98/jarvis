"""Loading and validation of the MCP server config file.

The config is a JSON file (path given by the ``MCP_CONFIG_PATH`` env var) shaped
like Claude Desktop's ``mcpServers`` block, but for remote Streamable HTTP servers
rather than local stdio subprocesses::

    {
      "mcpServers": {
        "gmail": {
          "url": "https://mcp.example.com/gmail/mcp",
          "headers": {"Authorization": "Bearer ${GMAIL_MCP_TOKEN}"},
          "default_risk_level": "external_write",
          "tool_risk_levels": {"gmail_search_messages": "safe_read_only"}
        }
      }
    }

String values support ``${VAR}`` expansion from the process environment so that
secrets (API keys, tokens) stay in ``.env`` / the deployment environment and are
never committed inside the JSON file. The file is parsed once at startup; MCP
connections are established lazily on first tool use (see ``MCPManager``).
"""

import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from agent_orchestration.exceptions import MCPConfigError
from agent_orchestration.tools.risk import ToolRiskLevel

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env_vars(value: str, *, context: str) -> str:
    """Replace every ``${VAR}`` in ``value`` with its environment value.

    Raises MCPConfigError naming ``context`` if a referenced variable is unset, so
    a missing secret fails loudly at startup rather than silently sending empty
    credentials to a server.
    """

    def _replace(match: re.Match[str]) -> str:
        var = match.group(1)
        env_value = os.environ.get(var)
        if env_value is None:
            raise MCPConfigError(
                f"{context}: environment variable '{var}' referenced in MCP config "
                f"is not set."
            )
        return env_value

    return _ENV_VAR_RE.sub(_replace, value)


def _expand_obj(obj: object, *, context: str) -> object:
    """Recursively expand ``${VAR}`` in all string values of a parsed-JSON object."""
    if isinstance(obj, str):
        return _expand_env_vars(obj, context=context)
    if isinstance(obj, dict):
        return {k: _expand_obj(v, context=context) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_obj(v, context=context) for v in obj]
    return obj


class MCPServerConfig(BaseModel):
    """Configuration for a single remote MCP server (Streamable HTTP)."""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    # MCP tools carry no risk classification, so we assign one here. Every tool
    # from this server defaults to ``default_risk_level``; ``tool_risk_levels``
    # overrides specific tools by their (un-namespaced) MCP tool name.
    default_risk_level: ToolRiskLevel = ToolRiskLevel.UNKNOWN
    tool_risk_levels: dict[str, ToolRiskLevel] = Field(default_factory=dict)
    # Per-request timeout (seconds) for connecting and calling this server.
    timeout: float = Field(default=30.0)

    def risk_for(self, tool_name: str) -> ToolRiskLevel:
        return self.tool_risk_levels.get(tool_name, self.default_risk_level)


class MCPConfig(BaseModel):
    """Parsed MCP config: a mapping of server name -> server config."""

    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


def load_mcp_config(path: str | Path) -> MCPConfig:
    """Load and validate the MCP config file at ``path``.

    Raises MCPConfigError if the file is missing, is not valid JSON, has an
    unexpected shape, or references an undefined environment variable.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise MCPConfigError(f"MCP config file not found: {config_path}")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MCPConfigError(f"MCP config file is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or "mcpServers" not in raw:
        raise MCPConfigError(
            "MCP config file must be a JSON object with a top-level 'mcpServers' key."
        )

    servers_block = raw["mcpServers"]
    if not isinstance(servers_block, dict):
        raise MCPConfigError("'mcpServers' must be a JSON object keyed by server name.")

    expanded = _expand_obj(servers_block, context="mcpServers")
    assert isinstance(expanded, dict)  # narrowed for mypy; shape checked above

    try:
        return MCPConfig(
            servers={
                name: MCPServerConfig.model_validate(cfg)
                for name, cfg in expanded.items()
            }
        )
    except ValidationError as exc:
        raise MCPConfigError(f"Invalid MCP server config: {exc}") from exc
