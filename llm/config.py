from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm.exceptions import ConfigurationError


class LLMConfig(BaseSettings):
    """LLM module configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ollama_base_url: str = Field(default="http://localhost:11434")
    default_model: str
    request_timeout: float = Field(default=60.0)
    default_temperature: float = Field(default=0.7)
    default_top_p: float = Field(default=0.9)
    default_max_tokens: int = Field(default=2048)

    @field_validator("default_model")
    @classmethod
    def model_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ConfigurationError("DEFAULT_MODEL must not be empty")
        return v

    @field_validator("request_timeout")
    @classmethod
    def timeout_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ConfigurationError("REQUEST_TIMEOUT must be a positive number")
        return v

    @field_validator("default_temperature")
    @classmethod
    def temperature_must_be_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 2.0):
            raise ConfigurationError("DEFAULT_TEMPERATURE must be between 0.0 and 2.0")
        return v

    @field_validator("default_top_p")
    @classmethod
    def top_p_must_be_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ConfigurationError("DEFAULT_TOP_P must be between 0.0 and 1.0")
        return v

    @field_validator("default_max_tokens")
    @classmethod
    def max_tokens_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ConfigurationError("DEFAULT_MAX_TOKENS must be a positive integer")
        return v
