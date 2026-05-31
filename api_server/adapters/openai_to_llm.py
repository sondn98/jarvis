import logging
from typing import Any

from llm.models import Message, MessageRole, ToolDefinition
from api_server.schemas.openai import ChatCompletionRequest, ChatMessage, Tool

logger = logging.getLogger(__name__)

_ROLE_MAP: dict[str, MessageRole] = {
    "system": MessageRole.SYSTEM,
    "user": MessageRole.USER,
    "assistant": MessageRole.ASSISTANT,
    "tool": MessageRole.TOOL,
    "function": MessageRole.TOOL,
}


def convert_role(role: str) -> MessageRole:
    """Convert an OpenAI role string to the internal MessageRole enum."""
    mapped = _ROLE_MAP.get(role.lower())
    if mapped is None:
        logger.debug("Unknown role '%s'; falling back to USER", role)
        return MessageRole.USER
    return mapped


def convert_message(message: ChatMessage) -> Message:
    """Convert a single OpenAI chat message to the internal Message model."""
    return Message(
        role=convert_role(message.role),
        content=message.content or "",
    )


def convert_messages(messages: list[ChatMessage]) -> list[Message]:
    """Convert OpenAI chat messages to internal Message models."""
    return [convert_message(m) for m in messages]


def convert_tool(tool: Tool) -> ToolDefinition:
    """Convert an OpenAI tool definition to the internal ToolDefinition model."""
    return ToolDefinition(
        name=tool.function.name,
        description=tool.function.description or "",
        parameters=tool.function.parameters,
    )


def convert_tools(tools: list[Tool]) -> list[ToolDefinition]:
    """Convert a list of OpenAI tool definitions to internal ToolDefinition models."""
    return [convert_tool(t) for t in tools]


def build_llm_kwargs(request: ChatCompletionRequest, default_model: str | None) -> dict[str, Any]:
    """Extract generation parameters from an OpenAI request as LLM service kwargs."""
    model = request.model or default_model
    kwargs: dict[str, Any] = {}
    if model:
        kwargs["model"] = model
    if request.temperature is not None:
        kwargs["temperature"] = request.temperature
    if request.top_p is not None:
        kwargs["top_p"] = request.top_p
    if request.max_tokens is not None:
        kwargs["max_tokens"] = request.max_tokens
    logger.debug("LLM kwargs: %s", kwargs)
    return kwargs
