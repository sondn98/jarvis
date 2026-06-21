import json

import pytest

from agent_orchestration.exceptions import MCPConfigError
from agent_orchestration.mcp.config import load_mcp_config
from agent_orchestration.tools.risk import ToolRiskLevel


def _write(tmp_path, data: dict) -> str:
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_load_basic_server(tmp_path):
    path = _write(
        tmp_path,
        {"mcpServers": {"gmail": {"url": "https://example.com/mcp"}}},
    )
    config = load_mcp_config(path)
    assert "gmail" in config.servers
    server = config.servers["gmail"]
    assert server.url == "https://example.com/mcp"
    # Unspecified risk defaults to UNKNOWN.
    assert server.default_risk_level is ToolRiskLevel.UNKNOWN


def test_env_var_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_TOKEN", "secret-123")
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "gmail": {
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer ${GMAIL_TOKEN}"},
                }
            }
        },
    )
    config = load_mcp_config(path)
    assert config.servers["gmail"].headers["Authorization"] == "Bearer secret-123"


def test_missing_env_var_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("ABSENT_TOKEN", raising=False)
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "gmail": {
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer ${ABSENT_TOKEN}"},
                }
            }
        },
    )
    with pytest.raises(MCPConfigError, match="ABSENT_TOKEN"):
        load_mcp_config(path)


def test_per_tool_risk_override(tmp_path):
    path = _write(
        tmp_path,
        {
            "mcpServers": {
                "gmail": {
                    "url": "https://example.com/mcp",
                    "default_risk_level": "external_write",
                    "tool_risk_levels": {"gmail_search_messages": "safe_read_only"},
                }
            }
        },
    )
    server = load_mcp_config(path).servers["gmail"]
    assert server.risk_for("gmail_send_email") is ToolRiskLevel.EXTERNAL_WRITE
    assert server.risk_for("gmail_search_messages") is ToolRiskLevel.SAFE_READ_ONLY


def test_missing_file_raises(tmp_path):
    with pytest.raises(MCPConfigError, match="not found"):
        load_mcp_config(str(tmp_path / "nope.json"))


def test_malformed_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(MCPConfigError, match="not valid JSON"):
        load_mcp_config(str(path))


def test_missing_mcpservers_key_raises(tmp_path):
    path = _write(tmp_path, {"servers": {}})
    with pytest.raises(MCPConfigError, match="mcpServers"):
        load_mcp_config(path)
