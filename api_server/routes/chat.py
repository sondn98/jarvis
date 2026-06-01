import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api_server.adapters.llm_to_openai import (
    convert_chat_response,
    convert_stream_chunk,
)
from api_server.adapters.openai_to_llm import (
    build_llm_kwargs,
    convert_messages,
    convert_tools,
)
from api_server.config import APIServerConfig
from api_server.dependencies import get_config, get_llm_service, verify_api_key
from api_server.errors import UnsupportedFeatureError
from api_server.schemas.openai import ChatCompletionRequest, ChatCompletionResponse
from llm.service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter()


async def _sse_generator(
    llm_service: LLMService,
    body: ChatCompletionRequest,
    request_id: str,
    **kwargs: object,
) -> AsyncIterator[str]:
    messages = convert_messages(body.messages)
    tools = convert_tools(body.tools) if body.tools else None
    first = True
    try:
        async for chunk in llm_service.stream_chat(messages, tools=tools, **kwargs):
            openai_chunk = convert_stream_chunk(
                chunk, body.model, request_id, first=first
            )
            first = False
            yield f"data: {openai_chunk.model_dump_json()}\n\n"
    except Exception:
        logger.exception("Error during streaming: request_id=%s", request_id)
        raise
    yield "data: [DONE]\n\n"


@router.post(
    "/chat/completions", dependencies=[Depends(verify_api_key)], response_model=None
)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
    config: Annotated[APIServerConfig, Depends(get_config)],
) -> ChatCompletionResponse | StreamingResponse:
    logger.info(
        "POST /v1/chat/completions: model=%s stream=%s", body.model, body.stream
    )

    if body.response_format and body.response_format.type != "text":
        raise UnsupportedFeatureError(
            f"response_format type '{body.response_format.type}' is not supported. Only 'text' is accepted."
        )

    kwargs = build_llm_kwargs(body, config.default_model)

    if body.stream:
        request_id = f"chatcmpl-{uuid4().hex}"
        return StreamingResponse(
            _sse_generator(llm_service, body, request_id, **kwargs),
            media_type="text/event-stream",
        )

    messages = convert_messages(body.messages)
    tools = convert_tools(body.tools) if body.tools else None
    llm_response = await llm_service.achat(messages, tools=tools, **kwargs)

    response = convert_chat_response(llm_response, body.model)
    logger.info(
        "POST /v1/chat/completions complete: finish_reason=%s",
        response.choices[0].finish_reason,
    )
    return response
