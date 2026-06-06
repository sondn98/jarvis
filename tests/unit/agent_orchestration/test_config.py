from agent_orchestration.config import AgentConfig


def test_defaults():
    config = AgentConfig()
    assert config.agent_enabled is True
    assert config.require_approval_for_sensitive_read is False
    assert config.require_approval_for_external_write is True
    assert config.require_approval_for_destructive is True
    assert config.require_approval_for_unknown is True
    assert config.enable_llm_risk_classifier is False


def test_env_override(monkeypatch):
    monkeypatch.setenv("REQUIRE_APPROVAL_FOR_SENSITIVE_READ", "true")
    monkeypatch.setenv("REQUIRE_APPROVAL_FOR_EXTERNAL_WRITE", "false")
    config = AgentConfig()
    assert config.require_approval_for_sensitive_read is True
    assert config.require_approval_for_external_write is False
