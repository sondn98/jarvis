from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class APIServerConfig(BaseSettings):
    """API server configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    # Precedence for "which model": the non-agent path uses the request's model,
    # falling back to this APIServerConfig.default_model. The agent path uses the
    # client's requested model, falling back to LLMConfig.default_model (the
    # provider default). These are two independent settings by design.
    default_model: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    enable_api_key_auth: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    enable_agent_orchestration: bool = Field(default=False)
