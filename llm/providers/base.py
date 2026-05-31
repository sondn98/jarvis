from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from llm.models import ChatResponse, Message, ToolDefinition


class BaseProvider(ABC):
    """Minimal interface that all LLM providers must implement."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat request and return a typed response."""

    @abstractmethod
    async def achat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Async variant of chat."""
