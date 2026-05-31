import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api_server.adapters.llm_to_openai import convert_chat_response
from api_server.adapters.openai_to_llm import build_llm_kwargs, convert_messages, convert_tools
from api_server.config import APIServerConfig
from api_server.dependencies import get_config, get_llm_service, verify_api_key
from api_server.errors import UnsupportedFeatureError
from api_server.schemas.openai import ChatCompletionRequest, ChatCompletionResponse
from llm.service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
    config: Annotated[APIServerConfig, Depends(get_config)],
) -> ChatCompletionResponse:
    logger.info("POST /v1/chat/completions: model=%s", body.model)

    if body.stream:
        raise UnsupportedFeatureError("Streaming is not supported yet.")

    if body.response_format and body.response_format.type != "text":
        raise UnsupportedFeatureError(
            f"response_format type '{body.response_format.type}' is not supported. Only 'text' is accepted."
        )

    messages = convert_messages(body.messages)
    tools = convert_tools(body.tools) if body.tools else None
    kwargs = build_llm_kwargs(body, config.default_model)

    llm_response = await llm_service.achat(messages, tools=tools, **kwargs)

    response = convert_chat_response(llm_response, body.model)
    logger.info("POST /v1/chat/completions complete: finish_reason=%s", response.choices[0].finish_reason)
    return response
