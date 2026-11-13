import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import litellm
import pytest
from pydantic import BaseModel

from llm.config import LLMConfig
from llm.exceptions import (
    LLMTimeoutError,
    ProviderError,
    StructuredOutputError,
    ToolCallParsingError,
)
from llm.models import Message, MessageRole
from llm.providers.litellm import (
    LiteLLMProvider,
    _build_chat_response,
    _to_litellm_message,
    _to_litellm_tool,
)
from logging_utils import TRACE

SDK = "llm.providers.litellm.litellm_sdk"


async def _async_iter(items):
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# Helpers to build fake LiteLLM (OpenAI-shaped) response objects
# ---------------------------------------------------------------------------


def _make_response(
    content: str | None = "",
    tool_calls=None,
    finish_reason: str = "stop",
) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    raw = MagicMock()
    raw.choices = [choice]
    return raw


def _make_tool_call(name: str, arguments, call_id: str | None = "call_1") -> MagicMock:
    fn = MagicMock()
    fn.name = name
    fn.arguments = arguments
    tc = MagicMock()
    tc.id = call_id
    tc.function = fn
    return tc


def _make_chunk(content: str | None, finish_reason: str | None = None) -> MagicMock:
    choice = MagicMock()
    choice.delta.content = content
    choice.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.model = "test-model"
    return chunk


def _usage_only_chunk() -> MagicMock:
    chunk = MagicMock()
    chunk.choices = []
    return chunk


class Plan(BaseModel):
    steps: list[str]


@pytest.fixture
def provider(base_config) -> LiteLLMProvider:
    return LiteLLMProvider(base_config)


# ---------------------------------------------------------------------------
# Translation helpers
# ---------------------------------------------------------------------------


class TestTranslation:
    def test_message(self):
        msg = Message(role=MessageRole.USER, content="Hello")
        assert _to_litellm_message(msg) == {"role": "user", "content": "Hello"}

    def test_tool(self, search_tool):
        assert _to_litellm_tool(search_tool) == {
            "type": "function",
            "function": {
                "name": "search_docs",
                "description": "Search internal documentation",
                "parameters": search_tool.parameters,
            },
        }


# ---------------------------------------------------------------------------
# _build_chat_response
# ---------------------------------------------------------------------------


class TestBuildChatResponse:
    def test_plain_content(self):
        result = _build_chat_response(_make_response(content="Hello!"), None)
        assert result.content == "Hello!"
        assert result.tool_calls == []
        assert result.finish_reason == "stop"

    def test_empty_content_becomes_none(self):
        result = _build_chat_response(_make_response(content=None), None)
        assert result.content is None

    def test_tool_call_with_json_string_arguments(self):
        tc = _make_tool_call("search_docs", '{"query": "test"}')
        raw = _make_response(content=None, tool_calls=[tc], finish_reason="tool_calls")
        result = _build_chat_response(raw, None)
        assert result.finish_reason == "tool_calls"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_1"
        assert result.tool_calls[0].name == "search_docs"
        assert result.tool_calls[0].arguments == {"query": "test"}

    def test_tool_call_with_dict_arguments(self):
        tc = _make_tool_call("search_docs", {"query": "test"})
        result = _build_chat_response(_make_response(tool_calls=[tc]), None)
        assert result.tool_calls[0].arguments == {"query": "test"}

    def test_tool_call_with_empty_arguments(self):
        tc = _make_tool_call("ping", "")
        result = _build_chat_response(_make_response(tool_calls=[tc]), None)
        assert result.tool_calls[0].arguments == {}

    def test_missing_tool_call_id_is_generated(self):
        tc = _make_tool_call("search_docs", "{}", call_id=None)
        result = _build_chat_response(_make_response(tool_calls=[tc]), None)
        assert result.tool_calls[0].id

    def test_invalid_json_arguments_raise(self):
        tc = _make_tool_call("search_docs", "{not json")
        with pytest.raises(ToolCallParsingError):
            _build_chat_response(_make_response(tool_calls=[tc]), None)

    def test_non_object_json_arguments_raise(self):
        tc = _make_tool_call("search_docs", "[1, 2]")
        with pytest.raises(ToolCallParsingError):
            _build_chat_response(_make_response(tool_calls=[tc]), None)

    def test_structured_output_valid(self):
        raw = _make_response(content='{"steps": ["a", "b"]}')
        result = _build_chat_response(raw, Plan)
        assert Plan.model_validate_json(result.content).steps == ["a", "b"]

    def test_structured_output_invalid_json(self):
        with pytest.raises(StructuredOutputError):
            _build_chat_response(_make_response(content="not json"), Plan)

    def test_structured_output_schema_mismatch(self):
        with pytest.raises(StructuredOutputError):
            _build_chat_response(_make_response(content='{"wrong": 1}'), Plan)


# ---------------------------------------------------------------------------
# chat / achat request forwarding
# ---------------------------------------------------------------------------


class TestChat:
    def test_forwards_defaults(self, provider, user_message):
        with patch(f"{SDK}.completion", return_value=_make_response("Hi")) as mock:
            result = provider.chat([user_message])

        assert result.content == "Hi"
        kwargs = mock.call_args.kwargs
        assert kwargs["model"] == "llama3.2"
        assert kwargs["messages"] == [{"role": "user", "content": "Hello"}]
        assert kwargs["tools"] is None
        assert kwargs["response_format"] is None
        assert kwargs["temperature"] == 0.7
        assert kwargs["top_p"] == 0.9
        assert kwargs["max_tokens"] == 2048
        assert kwargs["timeout"] == 60.0
        assert kwargs["drop_params"] is True
        assert kwargs["api_key"] is None
        assert kwargs["api_base"] is None

    def test_kwargs_override_defaults(self, provider, user_message, search_tool):
        with patch(f"{SDK}.completion", return_value=_make_response("Hi")) as mock:
            provider.chat(
                [user_message],
                tools=[search_tool],
                response_model=None,
                model="gemini/gemini-2.5-flash",
                temperature=0.1,
                top_p=0.5,
                max_tokens=10,
            )

        kwargs = mock.call_args.kwargs
        assert kwargs["model"] == "gemini/gemini-2.5-flash"
        assert kwargs["temperature"] == 0.1
        assert kwargs["top_p"] == 0.5
        assert kwargs["max_tokens"] == 10
        assert kwargs["tools"] == [_to_litellm_tool(search_tool)]

    def test_forwards_api_key_and_base(self, user_message):
        config = LLMConfig(
            default_model="m", llm_api_key="sk-secret", llm_api_base="http://h:1"
        )
        with patch(f"{SDK}.completion", return_value=_make_response("Hi")) as mock:
            LiteLLMProvider(config).chat([user_message])

        assert mock.call_args.kwargs["api_key"] == "sk-secret"
        assert mock.call_args.kwargs["api_base"] == "http://h:1"

    def test_response_model_forwarded(self, provider, user_message):
        raw = _make_response('{"steps": ["x"]}')
        with patch(f"{SDK}.completion", return_value=raw) as mock:
            provider.chat([user_message], response_model=Plan)

        assert mock.call_args.kwargs["response_format"] is Plan

    async def test_achat(self, provider, user_message):
        mock = AsyncMock(return_value=_make_response("Async!"))
        with patch(f"{SDK}.acompletion", new=mock):
            result = await provider.achat([user_message])

        assert result.content == "Async!"
        assert mock.call_args.kwargs["drop_params"] is True


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


_TIMEOUT = litellm.Timeout(message="timed out", model="m", llm_provider="p")
_BAD_REQUEST = litellm.BadRequestError(message="bad", model="m", llm_provider="p")
_UNSUPPORTED = litellm.UnsupportedParamsError(message="no top_p", model="m")


class TestErrorMapping:
    @pytest.mark.parametrize(
        "exc", [_TIMEOUT, httpx.ReadTimeout("slow"), TimeoutError("slow")]
    )
    def test_timeouts(self, provider, user_message, exc):
        with patch(f"{SDK}.completion", side_effect=exc):
            with pytest.raises(LLMTimeoutError):
                provider.chat([user_message])

    @pytest.mark.parametrize("exc", [_BAD_REQUEST, _UNSUPPORTED])
    def test_litellm_errors(self, provider, user_message, exc):
        with patch(f"{SDK}.completion", side_effect=exc):
            with pytest.raises(ProviderError) as info:
                provider.chat([user_message])
        assert "Unexpected" not in str(info.value)

    def test_unexpected_error(self, provider, user_message):
        with patch(f"{SDK}.completion", side_effect=RuntimeError("boom")):
            with pytest.raises(ProviderError, match="Unexpected error from LiteLLM"):
                provider.chat([user_message])

    async def test_achat_timeout(self, provider, user_message):
        with patch(f"{SDK}.acompletion", new=AsyncMock(side_effect=_TIMEOUT)):
            with pytest.raises(LLMTimeoutError):
                await provider.achat([user_message])

    def test_parsing_errors_not_remapped(self, provider, user_message):
        tc = _make_tool_call("x", "{bad")
        with patch(f"{SDK}.completion", return_value=_make_response(tool_calls=[tc])):
            with pytest.raises(ToolCallParsingError):
                provider.chat([user_message])


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


class TestAstreamChat:
    async def test_yields_chunks(self, provider, user_message):
        stream = _async_iter(
            [
                _make_chunk("Hel"),
                _make_chunk("lo"),
                _make_chunk(None, finish_reason="stop"),
                _usage_only_chunk(),
            ]
        )
        mock = AsyncMock(return_value=stream)
        with patch(f"{SDK}.acompletion", new=mock):
            results = [c async for c in provider.astream_chat([user_message])]

        assert mock.call_args.kwargs["stream"] is True
        assert [c.content for c in results] == ["Hel", "lo", ""]
        assert [c.done for c in results] == [False, False, True]
        assert results[-1].finish_reason == "stop"
        assert all(c.provider == "litellm" for c in results)
        assert all(c.model == "test-model" for c in results)

    async def test_mid_stream_error_is_mapped(self, provider, user_message):
        async def _broken():
            yield _make_chunk("partial")
            raise _BAD_REQUEST

        with patch(f"{SDK}.acompletion", new=AsyncMock(return_value=_broken())):
            with pytest.raises(ProviderError):
                [c async for c in provider.astream_chat([user_message])]

    async def test_stream_start_error_is_mapped(self, provider, user_message):
        with patch(f"{SDK}.acompletion", new=AsyncMock(side_effect=_TIMEOUT)):
            with pytest.raises(LLMTimeoutError):
                [c async for c in provider.astream_chat([user_message])]


# ---------------------------------------------------------------------------
# Model listing
# ---------------------------------------------------------------------------


class TestListModels:
    def test_list_models(self, provider):
        with patch(f"{SDK}.get_valid_models", return_value=["gemini/a", "openai/b"]):
            assert provider.list_models() == ["gemini/a", "openai/b"]

    async def test_alist_models(self, provider):
        with patch(f"{SDK}.get_valid_models", return_value=["gemini/a"]):
            assert await provider.alist_models() == ["gemini/a"]

    async def test_alist_models_queries_configured_endpoint(self):
        config = LLMConfig(
            default_model="litellm_proxy/gemini-x",
            llm_api_key="sk-proxy",
            llm_api_base="https://proxy.example/v1",
        )
        with patch(f"{SDK}.get_valid_models", return_value=["litellm_proxy/a"]) as gvm:
            assert await LiteLLMProvider(config).alist_models() == ["litellm_proxy/a"]
        gvm.assert_called_once_with(
            check_provider_endpoint=True,
            custom_llm_provider="litellm_proxy",
            api_key="sk-proxy",
            api_base="https://proxy.example/v1",
        )

    def test_list_models_empty_is_valid(self, provider):
        with patch(f"{SDK}.get_valid_models", return_value=[]):
            assert provider.list_models() == []

    def test_list_models_error(self, provider):
        with patch(f"{SDK}.get_valid_models", side_effect=RuntimeError("boom")):
            with pytest.raises(ProviderError):
                provider.list_models()

    async def test_alist_models_error(self, provider):
        with patch(f"{SDK}.get_valid_models", side_effect=RuntimeError("boom")):
            with pytest.raises(ProviderError):
                await provider.alist_models()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_api_key_never_logged_at_trace(user_message, caplog):
    config = LLMConfig(default_model="m", llm_api_key="sk-very-secret-key")
    provider = LiteLLMProvider(config)
    with patch(f"{SDK}.completion", return_value=_make_response("Hi")):
        with caplog.at_level(TRACE, logger="jarvis.llm"):
            provider.chat([user_message])

    assert any("request kwargs" in r.getMessage() for r in caplog.records)
    assert all("sk-very-secret-key" not in r.getMessage() for r in caplog.records)


def test_info_level_logs_no_content(provider, user_message, caplog):
    with patch(f"{SDK}.completion", return_value=_make_response("secret answer")):
        with caplog.at_level(logging.INFO, logger="jarvis.llm"):
            provider.chat([user_message])

    assert all("secret answer" not in r.getMessage() for r in caplog.records)
