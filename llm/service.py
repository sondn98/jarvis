from typing import Any

from pydantic import BaseModel

from llm.config import LLMConfig
from llm.models import ChatResponse, Message, MessageRole, ToolDefinition
from llm.providers.base import BaseProvider
from llm.providers.ollama import OllamaProvider


class LLMService:
    """Single access point for all LLM interactions.

    Usage::

        config = LLMConfig()
        llm = LLMService(config)

        # Simple generation
        response = llm.generate("Explain recursion in one sentence.")

        # Chat with tool definitions
        response = llm.chat(messages, tools=tools)

        # Structured output
        response = await llm.achat(messages, response_model=TaskPlan)
    """

    def __init__(self, config: LLMConfig, provider: BaseProvider | None = None) -> None:
        self._config = config
        self._provider: BaseProvider = provider or OllamaProvider(config)

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat request and return a typed response."""
        return self._provider.chat(messages, tools=tools, response_model=response_model, **kwargs)

    async def achat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Async variant of chat."""
        return await self._provider.achat(messages, tools=tools, response_model=response_model, **kwargs)

    def generate(self, prompt: str, **kwargs: Any) -> ChatResponse:
        """Send a single user prompt and return a typed response."""
        messages = [Message(role=MessageRole.USER, content=prompt)]
        return self.chat(messages, **kwargs)

    async def agenerate(self, prompt: str, **kwargs: Any) -> ChatResponse:
        """Async variant of generate."""
        messages = [Message(role=MessageRole.USER, content=prompt)]
        return await self.achat(messages, **kwargs)

    def list_models(self) -> list[str]:
        """Return names of models available from the configured provider."""
        return self._provider.list_models()

    async def alist_models(self) -> list[str]:
        """Async variant of list_models."""
        return await self._provider.alist_models()
