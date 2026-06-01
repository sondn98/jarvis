import json
import logging
import time
from uuid import uuid4

from llm.models import ChatResponse, LLMStreamChunk, ToolCall
from api_server.schemas.openai import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionMessage,
    ChatCompletionResponse,
    ChatToolCall,
    ToolCallFunction,
)

logger = logging.getLogger(__name__)

_FINISH_REASON_MAP: dict[str, str] = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "tool_call": "tool_calls",
    "content_filter": "content_filter",
}


def convert_finish_reason(reason: str | None) -> str:
    """Convert an internal finish reason to the OpenAI finish_reason string."""
    if reason is None:
        return "stop"
    return _FINISH_REASON_MAP.get(reason.lower(), reason)


def convert_tool_call(tool_call: ToolCall) -> ChatToolCall:
    """Convert an internal ToolCall to an OpenAI-compatible ChatToolCall."""
    return ChatToolCall(
        id=tool_call.id,
        type="function",
        function=ToolCallFunction(
            name=tool_call.name,
            arguments=json.dumps(tool_call.arguments),
        ),
    )


def convert_tool_calls(tool_calls: list[ToolCall]) -> list[ChatToolCall]:
    """Convert a list of internal ToolCall objects to OpenAI ChatToolCall objects."""
    return [convert_tool_call(tc) for tc in tool_calls]


def convert_chat_response(
    llm_response: ChatResponse,
    model: str,
    request_id: str | None = None,
) -> ChatCompletionResponse:
    """Convert an internal ChatResponse to an OpenAI ChatCompletionResponse."""
    has_tool_calls = bool(llm_response.tool_calls)

    openai_tool_calls = (
        convert_tool_calls(llm_response.tool_calls) if has_tool_calls else None
    )
    finish_reason = (
        "tool_calls"
        if has_tool_calls
        else convert_finish_reason(llm_response.finish_reason)
    )

    message = ChatCompletionMessage(
        role="assistant",
        content=llm_response.content,
        tool_calls=openai_tool_calls,
    )
    choice = ChatCompletionChoice(index=0, message=message, finish_reason=finish_reason)

    response_id = request_id or f"chatcmpl-{uuid4().hex}"
    logger.debug(
        "Converted LLM response: id=%s finish_reason=%s", response_id, finish_reason
    )

    return ChatCompletionResponse(
        id=response_id,
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[choice],
    )


def convert_stream_chunk(
    chunk: LLMStreamChunk,
    model: str,
    request_id: str,
    *,
    first: bool,
) -> ChatCompletionChunk:
    """Convert an LLMStreamChunk to an OpenAI-compatible chat.completion.chunk."""
    if first:
        delta = ChatCompletionChunkDelta(role="assistant", content=chunk.content)
    else:
        delta = ChatCompletionChunkDelta(content=chunk.content)

    finish_reason = convert_finish_reason(chunk.finish_reason) if chunk.done else None

    return ChatCompletionChunk(
        id=request_id,
        created=int(time.time()),
        model=model,
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=delta,
                finish_reason=finish_reason,
            )
        ],
    )
