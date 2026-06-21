import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import ollama as ollama_sdk
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


def _to_ollama_message(message: Message) -> dict[str, Any]:
    return {"role": message.role.value, "content": message.content}


def _to_ollama_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    result = []
    try:
        for tc in raw_tool_calls:
            fn = tc.function
            result.append(
                ToolCall(
                    id=str(uuid4()),
                    name=fn.name,
                    arguments=dict(fn.arguments) if fn.arguments else {},
                )
            )
    except Exception as exc:
        raise ToolCallParsingError(f"Failed to parse tool calls: {exc}") from exc
    return result


def _build_chat_response(
    raw: ollama_sdk.ChatResponse, response_model: type[BaseModel] | None
) -> ChatResponse:
    message = raw.message
    tool_calls: list[ToolCall] = []

    if message.tool_calls:
        tool_calls = _parse_tool_calls(message.tool_calls)
        return ChatResponse(
            content=message.content or None,
            tool_calls=tool_calls,
            finish_reason=raw.done_reason,
        )

    if response_model is not None:
        content = message.content or ""
        try:
            parsed = response_model.model_validate_json(content)
            return ChatResponse(
                content=parsed.model_dump_json(),
                tool_calls=[],
                finish_reason=raw.done_reason,
            )
        except (ValidationError, json.JSONDecodeError) as exc:
            raise StructuredOutputError(
                f"Structured output validation failed for {response_model.__name__}: {exc}"
            ) from exc

    return ChatResponse(
        content=message.content or None,
        tool_calls=[],
        finish_reason=raw.done_reason,
    )


def _map_error(exc: Exception) -> LLMError:
    """Map a raw exception from the Ollama SDK/transport to an LLM error.

    Ollama is backed by httpx, so timeouts surface as ``httpx.TimeoutException``
    (not the builtin ``TimeoutError``); both are translated to
    ``LLMTimeoutError`` so the 504 path is reachable.
    """
    if isinstance(exc, ollama_sdk.ResponseError):
        logger.error("Provider error: %s", exc)
        return ProviderError(str(exc))
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        logger.error("Request timed out: %s", exc)
        return LLMTimeoutError(str(exc))
    logger.error("Unexpected provider error: %s", exc)
    return ProviderError(f"Unexpected error from Ollama: {exc}")


class OllamaProvider(BaseProvider):
    """LLM provider backed by the official Ollama Python SDK."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = ollama_sdk.Client(
            host=config.ollama_base_url,
            timeout=config.request_timeout,
        )
        self._async_client = ollama_sdk.AsyncClient(
            host=config.ollama_base_url,
            timeout=config.request_timeout,
        )

    def _build_options(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "temperature": kwargs.get("temperature", self._config.default_temperature),
            "top_p": kwargs.get("top_p", self._config.default_top_p),
            "num_predict": kwargs.get("max_tokens", self._config.default_max_tokens),
        }

    def _build_format(
        self, response_model: type[BaseModel] | None
    ) -> dict[str, Any] | None:
        if response_model is None:
            return None
        return response_model.model_json_schema()

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_model: type[BaseModel] | None,
        **kwargs: Any,
    ) -> tuple[
        str,
        list[dict[str, Any]],
        list[dict[str, Any]] | None,
        dict[str, Any],
        dict[str, Any] | None,
    ]:
        model = kwargs.get("model", self._config.default_model)
        ollama_messages = [_to_ollama_message(m) for m in messages]
        ollama_tools = [_to_ollama_tool(t) for t in tools] if tools else None
        options = self._build_options(**kwargs)
        fmt = self._build_format(response_model)
        return model, ollama_messages, ollama_tools, options, fmt

    def _log_request(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response_model: type[BaseModel] | None,
        options: dict[str, Any],
        fmt: dict[str, Any] | None,
        *,
        label: str,
    ) -> None:
        logger.debug(
            "LLM %srequest: model=%s, messages=%d, tools=%s, schema=%s",
            label,
            model,
            len(messages),
            [t.name for t in tools] if tools else None,
            response_model.__name__ if response_model else None,
        )
        if logger.isEnabledFor(TRACE):
            logger.log(
                TRACE,
                "LLM full messages: %s",
                [_to_ollama_message(m) for m in messages],
            )
            logger.log(
                TRACE,
                "LLM request kwargs: model=%s options=%s format=%s",
                model,
                options,
                fmt,
            )

    def _log_response(
        self, response: ChatResponse, raw: ollama_sdk.ChatResponse, *, label: str
    ) -> None:
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
            if hasattr(raw, "prompt_eval_count"):
                logger.log(
                    TRACE,
                    "Token usage: prompt=%s eval=%s",
                    getattr(raw, "prompt_eval_count", None),
                    getattr(raw, "eval_count", None),
                )

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        model, ollama_messages, ollama_tools, options, fmt = self._prepare_request(
            messages, tools, response_model, **kwargs
        )
        self._log_request(
            model, messages, tools, response_model, options, fmt, label=""
        )

        try:
            raw = self._client.chat(
                model=model,
                messages=ollama_messages,
                tools=ollama_tools,
                format=fmt,
                options=options,
            )
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
        model, ollama_messages, ollama_tools, options, fmt = self._prepare_request(
            messages, tools, response_model, **kwargs
        )
        self._log_request(
            model, messages, tools, response_model, options, fmt, label="async "
        )

        try:
            raw = await self._async_client.chat(
                model=model,
                messages=ollama_messages,
                tools=ollama_tools,
                format=fmt,
                options=options,
            )
        except Exception as exc:
            raise _map_error(exc) from exc

        response = _build_chat_response(raw, response_model)
        self._log_response(response, raw, label="async ")
        return response

    def list_models(self) -> list[str]:
        logger.info("Listing available Ollama models")
        try:
            result = self._client.list()
            return [m.model for m in result.models]
        except ollama_sdk.ResponseError as exc:
            logger.error("Provider error listing models: %s", exc)
            raise ProviderError(str(exc)) from exc
        except Exception as exc:
            logger.error("Unexpected error listing models: %s", exc)
            raise ProviderError(f"Unexpected error from Ollama: {exc}") from exc

    async def alist_models(self) -> list[str]:
        logger.info("Listing available Ollama models (async)")
        try:
            result = await self._async_client.list()
            return [m.model for m in result.models]
        except ollama_sdk.ResponseError as exc:
            logger.error("Provider error listing models: %s", exc)
            raise ProviderError(str(exc)) from exc
        except Exception as exc:
            logger.error("Unexpected error listing models: %s", exc)
            raise ProviderError(f"Unexpected error from Ollama: {exc}") from exc

    async def astream_chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        model, ollama_messages, ollama_tools, options, _ = self._prepare_request(
            messages, tools, None, **kwargs
        )

        logger.debug("Stream started: model=%s", model)
        t0 = time.monotonic()
        chunk_count = 0
        try:
            response = await self._async_client.chat(
                model=model,
                messages=ollama_messages,
                tools=ollama_tools,
                options=options,
                stream=True,
            )
            async for chunk in response:
                chunk_count += 1
                if logger.isEnabledFor(TRACE):
                    logger.log(
                        TRACE, "Stream chunk %d: %r", chunk_count, chunk.message.content
                    )
                yield LLMStreamChunk(
                    content=chunk.message.content or "",
                    done=chunk.done or False,
                    provider="ollama",
                    model=chunk.model,
                    finish_reason=chunk.done_reason if chunk.done else None,
                    raw=None,
                )
        except Exception as exc:
            raise _map_error(exc) from exc
        else:
            duration_ms = (time.monotonic() - t0) * 1000
            logger.debug(
                "Stream completed: model=%s, chunks=%d, duration=%.0fms",
                model,
                chunk_count,
                duration_ms,
            )
