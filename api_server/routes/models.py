import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api_server.dependencies import get_llm_service, verify_api_key
from api_server.schemas.openai import ModelListResponse, ModelObject
from llm.service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/models", dependencies=[Depends(verify_api_key)])
async def list_models(
    request: Request,
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
) -> ModelListResponse:
    logger.info("GET /v1/models")
    model_names = await llm_service.alist_models()
    data = [ModelObject(id=name) for name in model_names]
    logger.info("GET /v1/models complete: %d models", len(data))
    return ModelListResponse(data=data)
