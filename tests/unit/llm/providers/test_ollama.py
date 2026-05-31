from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from llm.config import LLMConfig
from llm.exceptions import ProviderError, StructuredOutputError, ToolCallParsingError
from llm.models import Message, MessageRole
from llm.providers.ollama import (
    OllamaProvider,
    _build_chat_response,
    _to_ollama_message,
    _to_ollama_tool,
)


# ---------------------------------------------------------------------------
# Helpers to build fake Ollama SDK objects
# ---------------------------------------------------------------------------


def _make_ollama_response(
    content: str = "",
    tool_calls=None,
    done_reason: str = "stop",
) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    raw = MagicMock()
    raw.message = msg
    raw.done_reason = done_reason
    return raw


def _make_ollama_tool_call(name: str, arguments: dict) -> MagicMock:
    fn = MagicMock()
    fn.name = name
    fn.arguments = arguments
    tc = MagicMock()
    tc.function = fn
    return tc


# ---------------------------------------------------------------------------
# Translation helpers
# ---------------------------------------------------------------------------


class TestToOllamaMessage:
    def test_user_message(self):
        msg = Message(role=MessageRole.USER, content="Hello")
        result = _to_ollama_message(msg)
        assert result == {"role": "user", "content": "Hello"}

    def test_system_message(self):
        msg = Message(role=MessageRole.SYSTEM, content="Be helpful.")
        result = _to_ollama_message(msg)
        assert result == {"role": "system", "content": "Be helpful."}


class TestToOllamaTool:
    def test_tool_translation(self, search_tool):
        result = _to_ollama_tool(search_tool)
        assert result["type"] == "function"
        assert result["function"]["name"] == "search_docs"
        assert result["function"]["description"] == "Search internal documentation"
        assert "properties" in result["function"]["parameters"]


# ---------------------------------------------------------------------------
# _build_chat_response
# ---------------------------------------------------------------------------


class TestBuildChatResponse:
    def test_plain_text_response(self):
        raw = _make_ollama_response(content="Hello!", done_reason="stop")
        resp = _build_chat_response(raw, response_model=None)
        assert resp.content == "Hello!"
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"

    def test_tool_call_response(self):
        tc = _make_ollama_tool_call("search_docs", {"query": "test"})
        raw = _make_ollama_response(
            content="", tool_calls=[tc], done_reason="tool_calls"
        )
        resp = _build_chat_response(raw, response_model=None)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "search_docs"
        assert resp.tool_calls[0].arguments == {"query": "test"}

    def test_structured_output_valid(self):
        class Plan(BaseModel):
            steps: list[str]

        raw = _make_ollama_response(content='{"steps": ["a", "b"]}', done_reason="stop")
        resp = _build_chat_response(raw, response_model=Plan)
        assert resp.content == '{"steps":["a","b"]}'

    def test_structured_output_invalid_raises(self):
        class Plan(BaseModel):
            steps: list[str]

        raw = _make_ollama_response(content="not json", done_reason="stop")
        with pytest.raises(StructuredOutputError):
            _build_chat_response(raw, response_model=Plan)

    def test_structured_output_wrong_schema_raises(self):
        class Plan(BaseModel):
            steps: list[str]

        raw = _make_ollama_response(content='{"wrong_field": 1}', done_reason="stop")
        with pytest.raises(StructuredOutputError):
            _build_chat_response(raw, response_model=Plan)

    def test_malformed_tool_call_raises(self):
        broken_tc = MagicMock()
        broken_tc.function = None  # will raise AttributeError during parsing
        raw = _make_ollama_response(tool_calls=[broken_tc], done_reason="tool_calls")
        with pytest.raises(ToolCallParsingError):
            _build_chat_response(raw, response_model=None)


# ---------------------------------------------------------------------------
# OllamaProvider.chat
# ---------------------------------------------------------------------------


@pytest.fixture
def config():
    return LLMConfig(default_model="llama3.2")


@pytest.fixture
def provider(config):
    with (
        patch("llm.providers.ollama.ollama_sdk.Client"),
        patch("llm.providers.ollama.ollama_sdk.AsyncClient"),
    ):
        return OllamaProvider(config)


class TestOllamaProviderChat:
    def test_successful_chat(self, provider, user_message):
        raw = _make_ollama_response(content="Hi!", done_reason="stop")
        provider._client.chat.return_value = raw

        resp = provider.chat([user_message])

        assert resp.content == "Hi!"
        provider._client.chat.assert_called_once()

    def test_chat_with_tools(self, provider, user_message, search_tool):
        tc = _make_ollama_tool_call("search_docs", {"query": "hello"})
        raw = _make_ollama_response(
            content="", tool_calls=[tc], done_reason="tool_calls"
        )
        provider._client.chat.return_value = raw

        resp = provider.chat([user_message], tools=[search_tool])

        assert len(resp.tool_calls) == 1
        call_kwargs = provider._client.chat.call_args.kwargs
        assert call_kwargs["tools"] is not None

    def test_provider_error_raises(self, provider, user_message):
        import ollama as sdk

        provider._client.chat.side_effect = sdk.ResponseError("model not found")
        with pytest.raises(ProviderError):
            provider.chat([user_message])

    def test_unexpected_error_raises(self, provider, user_message):
        provider._client.chat.side_effect = RuntimeError("connection refused")
        with pytest.raises(ProviderError):
            provider.chat([user_message])

    def test_timeout_raises(self, provider, user_message):
        from llm.exceptions import TimeoutError as LLMTimeout

        provider._client.chat.side_effect = LLMTimeout("timed out")
        with pytest.raises(LLMTimeout):
            provider.chat([user_message])


class TestOllamaProviderAchat:
    @pytest.mark.asyncio
    async def test_async_chat_returns_response(self, provider, user_message):
        raw = _make_ollama_response(content="Async!", done_reason="stop")
        provider._async_client.chat = AsyncMock(return_value=raw)

        resp = await provider.achat([user_message])

        assert resp.content == "Async!"

    @pytest.mark.asyncio
    async def test_async_provider_error_raises(self, provider, user_message):
        import ollama as sdk

        provider._async_client.chat = AsyncMock(
            side_effect=sdk.ResponseError("unavailable")
        )
        with pytest.raises(ProviderError):
            await provider.achat([user_message])
