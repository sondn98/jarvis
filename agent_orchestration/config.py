from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """Agent orchestration configuration loaded from environment variables.

    SENSITIVE_READ operations may expose private user data.
    Set require_approval_for_sensitive_read=True if stricter privacy control is desired.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    agent_enabled: bool = Field(default=True)
    require_approval_for_sensitive_read: bool = Field(default=False)
    require_approval_for_external_write: bool = Field(default=True)
    require_approval_for_destructive: bool = Field(default=True)
    require_approval_for_unknown: bool = Field(default=True)
    enable_llm_risk_classifier: bool = Field(default=False)
