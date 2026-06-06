from agent_orchestration.approval.policy import ApprovalPolicy
from agent_orchestration.config import AgentConfig
from agent_orchestration.tools.risk import ToolRiskLevel


def _policy(**overrides) -> ApprovalPolicy:
    return ApprovalPolicy(AgentConfig(**overrides))


def test_safe_read_never_requires_approval():
    policy = _policy()
    assert policy.requires_approval(ToolRiskLevel.SAFE_READ_ONLY) is False


def test_sensitive_read_default_no_approval():
    policy = _policy()
    assert policy.requires_approval(ToolRiskLevel.SENSITIVE_READ) is False


def test_sensitive_read_requires_approval_when_configured():
    policy = _policy(require_approval_for_sensitive_read=True)
    assert policy.requires_approval(ToolRiskLevel.SENSITIVE_READ) is True


def test_external_write_requires_approval_by_default():
    policy = _policy()
    assert policy.requires_approval(ToolRiskLevel.EXTERNAL_WRITE) is True


def test_external_write_no_approval_when_disabled():
    policy = _policy(require_approval_for_external_write=False)
    assert policy.requires_approval(ToolRiskLevel.EXTERNAL_WRITE) is False


def test_destructive_requires_approval_by_default():
    policy = _policy()
    assert policy.requires_approval(ToolRiskLevel.DESTRUCTIVE) is True


def test_unknown_requires_approval_by_default():
    policy = _policy()
    assert policy.requires_approval(ToolRiskLevel.UNKNOWN) is True
