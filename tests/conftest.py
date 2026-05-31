import pytest

from llm.config import LLMConfig
from llm.models import Message, MessageRole, ToolDefinition


@pytest.fixture
def base_config() -> LLMConfig:
    return LLMConfig(default_model="llama3.2")


@pytest.fixture
def user_message() -> Message:
    return Message(role=MessageRole.USER, content="Hello")


@pytest.fixture
def system_message() -> Message:
    return Message(role=MessageRole.SYSTEM, content="You are a helpful assistant.")


@pytest.fixture
def search_tool() -> ToolDefinition:
    return ToolDefinition(
        name="search_docs",
        description="Search internal documentation",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
