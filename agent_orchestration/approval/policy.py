from agent_orchestration.config import AgentConfig
from agent_orchestration.tools.risk import ToolRiskLevel


class ApprovalPolicy:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def requires_approval(self, risk_level: ToolRiskLevel) -> bool:
        if risk_level == ToolRiskLevel.SAFE_READ_ONLY:
            return False
        if risk_level == ToolRiskLevel.SENSITIVE_READ:
            return self._config.require_approval_for_sensitive_read
        if risk_level == ToolRiskLevel.EXTERNAL_WRITE:
            return self._config.require_approval_for_external_write
        if risk_level == ToolRiskLevel.DESTRUCTIVE:
            return self._config.require_approval_for_destructive
        # UNKNOWN
        return self._config.require_approval_for_unknown
