from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from llm.exceptions import StreamingNotSupportedError
from llm.models import ChatResponse, LLMStreamChunk, Message, ToolDefinition


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

    async def astream_chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a chat response as an async iterator of chunks.

        Providers that support streaming must override this method.
        The default raises StreamingNotSupportedError.
        """
        raise StreamingNotSupportedError(
            f"{type(self).__name__} does not support streaming."
        )
        yield  # type: ignore[misc]  # makes this an async generator

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return names of models available on this provider."""

    @abstractmethod
    async def alist_models(self) -> list[str]:
        """Async variant of list_models."""
