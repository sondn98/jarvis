import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import litellm as litellm_sdk
from pydantic import BaseModel, ValidationError

from llm.config import LLMConfig
from llm.exceptions import (
    LLMError,
    LLMTimeoutError,
    ProviderError,
    StructuredOutputError,
    ToolCallParsingError,
)
from llm.models import ChatResponse, LLMStreamChunk, Message, ToolCall, ToolDefinition
from llm.providers.base import BaseProvider
from logging_utils import TRACE

logger = logging.getLogger("jarvis.llm")

# Every exception type LiteLLM raises for provider/API failures.
_LITELLM_ERRORS = tuple(litellm_sdk.exceptions.LITELLM_EXCEPTION_TYPES)


def _to_litellm_message(message: Message) -> dict[str, Any]:
    return {"role": message.role.value, "content": message.content}


def _to_litellm_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _parse_arguments(raw_arguments: Any) -> dict[str, Any]:
    if not raw_arguments:
        return {}
    if isinstance(raw_arguments, str):
        raw_arguments = json.loads(raw_arguments)
    if not isinstance(raw_arguments, dict):
        raise TypeError(
            f"arguments must be a JSON object, got {type(raw_arguments).__name__}"
        )
    return raw_arguments


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    result = []
    try:
        for tc in raw_tool_calls:
            fn = tc.function
            result.append(
                ToolCall(
                    id=tc.id or str(uuid4()),
                    name=fn.name,
                    arguments=_parse_arguments(fn.arguments),
                )
            )
    except Exception as exc:
        raise ToolCallParsingError(f"Failed to parse tool calls: {exc}") from exc
    return result


def _build_chat_response(
    raw: Any, response_model: type[BaseModel] | None
) -> ChatResponse:
    choice = raw.choices[0]
    message = choice.message

    if message.tool_calls:
        return ChatResponse(
            content=message.content or None,
            tool_calls=_parse_tool_calls(message.tool_calls),
            finish_reason=choice.finish_reason,
        )

    if response_model is not None:
        content = message.content or ""
        try:
            parsed = response_model.model_validate_json(content)
            return ChatResponse(
                content=parsed.model_dump_json(),
                tool_calls=[],
                finish_reason=choice.finish_reason,
            )
        except (ValidationError, json.JSONDecodeError) as exc:
            raise StructuredOutputError(
                f"Structured output validation failed for {response_model.__name__}: {exc}"
            ) from exc

    return ChatResponse(
        content=message.content or None,
        tool_calls=[],
        finish_reason=choice.finish_reason,
    )


def _map_error(exc: Exception) -> LLMError:
    """Map a raw exception from LiteLLM/transport to an LLM error.

    ``litellm.Timeout`` is itself one of LiteLLM's API error types, so it must
    be checked before the generic LiteLLM branch to keep the 504 path reachable.
    """
    if isinstance(exc, (litellm_sdk.Timeout, httpx.TimeoutException, TimeoutError)):
        logger.error("Request timed out: %s", exc)
        return LLMTimeoutError(str(exc))
    if isinstance(exc, _LITELLM_ERRORS):
        logger.error("Provider error: %s", exc)
        return ProviderError(str(exc))
    logger.error("Unexpected provider error: %s", exc)
    return ProviderError(f"Unexpected error from LiteLLM: {exc}")


class LiteLLMProvider(BaseProvider):
    """LLM provider backed by the LiteLLM SDK (any LiteLLM-supported model)."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_model: type[BaseModel] | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        api_key = self._config.llm_api_key
        return {
            "model": kwargs.get("model", self._config.default_model),
            "messages": [_to_litellm_message(m) for m in messages],
            "tools": [_to_litellm_tool(t) for t in tools] if tools else None,
            "response_format": response_model,
            "temperature": kwargs.get("temperature", self._config.default_temperature),
            "top_p": kwargs.get("top_p", self._config.default_top_p),
            "max_tokens": kwargs.get("max_tokens", self._config.default_max_tokens),
            "timeout": self._config.request_timeout,
            "api_key": api_key.get_secret_value() if api_key else None,
            "api_base": self._config.llm_api_base,
            "drop_params": True,
        }

    def _log_request(
        self,
        request: dict[str, Any],
        tools: list[ToolDefinition] | None,
        response_model: type[BaseModel] | None,
        *,
        label: str,
    ) -> None:
        logger.debug(
            "LLM %srequest: model=%s, messages=%d, tools=%s, schema=%s",
            label,
            request["model"],
            len(request["messages"]),
            [t.name for t in tools] if tools else None,
            response_model.__name__ if response_model else None,
        )
        if logger.isEnabledFor(TRACE):
            logger.log(TRACE, "LLM full messages: %s", request["messages"])
            logger.log(
                TRACE,
                "LLM request kwargs: model=%s api_base=%s temperature=%s top_p=%s "
                "max_tokens=%s timeout=%s response_format=%s",
                request["model"],
                request["api_base"],
                request["temperature"],
                request["top_p"],
                request["max_tokens"],
                request["timeout"],
                response_model.__name__ if response_model else None,
            )

    def _log_response(self, response: ChatResponse, raw: Any, *, label: str) -> None:
        logger.debug(
            "LLM %sresponse: finish_reason=%s, tool_calls=%d, content_len=%s",
            label,
            response.finish_reason,
            len(response.tool_calls),
            len(response.content) if response.content else 0,
        )
        if logger.isEnabledFor(TRACE):
            logger.log(TRACE, "LLM raw response: %s", raw)
            logger.log(TRACE, "LLM response content: %s", response.content)
            usage = getattr(raw, "usage", None)
            if usage is not None:
                logger.log(
                    TRACE,
                    "Token usage: prompt=%s completion=%s",
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                )

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        request = self._prepare_request(messages, tools, response_model, **kwargs)
        self._log_request(request, tools, response_model, label="")

        try:
            raw = litellm_sdk.completion(**request)
        except Exception as exc:
            raise _map_error(exc) from exc

        response = _build_chat_response(raw, response_model)
        self._log_response(response, raw, label="")
        return response

    async def achat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        request = self._prepare_request(messages, tools, response_model, **kwargs)
        self._log_request(request, tools, response_model, label="async ")

        try:
            raw = await litellm_sdk.acompletion(**request)
        except Exception as exc:
            raise _map_error(exc) from exc

        response = _build_chat_response(raw, response_model)
        self._log_response(response, raw, label="async ")
        return response

    def _list_models_kwargs(self) -> dict[str, Any]:
        """Arguments for ``get_valid_models`` derived from our config.

        Without them LiteLLM only looks at provider env vars (e.g.
        ``OPENAI_API_KEY``) and silently returns ``[]`` when none are set —
        it never queries the configured ``llm_api_base``.
        """
        try:
            _, provider, _, _ = litellm_sdk.get_llm_provider(self._config.default_model)
        except Exception:
            provider = None
        api_key = self._config.llm_api_key
        return {
            "check_provider_endpoint": True,
            "custom_llm_provider": provider,
            "api_key": api_key.get_secret_value() if api_key else None,
            "api_base": self._config.llm_api_base,
        }

    def list_models(self) -> list[str]:
        logger.info("Listing available LiteLLM models")
        try:
            return list(litellm_sdk.get_valid_models(**self._list_models_kwargs()))
        except Exception as exc:
            raise _map_error(exc) from exc

    async def alist_models(self) -> list[str]:
        logger.info("Listing available LiteLLM models (async)")
        try:
            return list(
                await asyncio.to_thread(
                    litellm_sdk.get_valid_models, **self._list_models_kwargs()
                )
            )
        except Exception as exc:
            raise _map_error(exc) from exc

    async def astream_chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        request = self._prepare_request(messages, tools, None, **kwargs)

        logger.debug("Stream started: model=%s", request["model"])
        t0 = time.monotonic()
        chunk_count = 0
        try:
            response = await litellm_sdk.acompletion(**request, stream=True)
            async for chunk in response:
                if not chunk.choices:
                    continue
                chunk_count += 1
                choice = chunk.choices[0]
                content = choice.delta.content or ""
                if logger.isEnabledFor(TRACE):
                    logger.log(TRACE, "Stream chunk %d: %r", chunk_count, content)
                yield LLMStreamChunk(
                    content=content,
                    done=choice.finish_reason is not None,
                    provider="litellm",
                    model=chunk.model,
                    finish_reason=choice.finish_reason,
                    raw=None,
                )
        except Exception as exc:
            raise _map_error(exc) from exc
        else:
            duration_ms = (time.monotonic() - t0) * 1000
            logger.debug(
                "Stream completed: model=%s, chunks=%d, duration=%.0fms",
                request["model"],
                chunk_count,
                duration_ms,
            )
