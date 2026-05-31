import pytest
from pydantic import ValidationError

from llm.config import LLMConfig
from llm.exceptions import ConfigurationError


def test_valid_config():
    config = LLMConfig(default_model="llama3.2")
    assert config.default_model == "llama3.2"
    assert config.ollama_base_url == "http://localhost:11434"
    assert config.request_timeout == 60.0
    assert config.default_temperature == 0.7
    assert config.default_top_p == 0.9
    assert config.default_max_tokens == 2048


def test_custom_values():
    config = LLMConfig(
        default_model="mistral",
        ollama_base_url="http://myhost:11434",
        request_timeout=30.0,
        default_temperature=0.5,
        default_top_p=0.8,
        default_max_tokens=1024,
    )
    assert config.default_model == "mistral"
    assert config.ollama_base_url == "http://myhost:11434"
    assert config.request_timeout == 30.0


def test_missing_model_raises():
    with pytest.raises(ValidationError):
        LLMConfig()


def test_empty_model_raises():
    with pytest.raises(ConfigurationError):
        LLMConfig(default_model="   ")


def test_negative_timeout_raises():
    with pytest.raises(ConfigurationError):
        LLMConfig(default_model="llama3.2", request_timeout=-1.0)


def test_zero_timeout_raises():
    with pytest.raises(ConfigurationError):
        LLMConfig(default_model="llama3.2", request_timeout=0.0)


def test_temperature_out_of_range_raises():
    with pytest.raises(ConfigurationError):
        LLMConfig(default_model="llama3.2", default_temperature=3.0)


def test_top_p_out_of_range_raises():
    with pytest.raises(ConfigurationError):
        LLMConfig(default_model="llama3.2", default_top_p=1.5)


def test_negative_max_tokens_raises():
    with pytest.raises(ConfigurationError):
        LLMConfig(default_model="llama3.2", default_max_tokens=0)
