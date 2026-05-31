import logging

from fastapi import Request

from api_server.config import APIServerConfig
from api_server.errors import AuthenticationError
from llm.service import LLMService

logger = logging.getLogger(__name__)


def get_config(request: Request) -> APIServerConfig:
    """FastAPI dependency that returns the APIServerConfig from app state."""
    return request.app.state.config


def get_llm_service(request: Request) -> LLMService:
    """FastAPI dependency that returns the LLMService from app state."""
    return request.app.state.llm_service


async def verify_api_key(request: Request) -> None:
    """FastAPI dependency that enforces API key authentication when enabled."""
    config: APIServerConfig = request.app.state.config
    if not config.enable_api_key_auth:
        return
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header.")
    token = authorization[7:]
    if not config.api_key or token != config.api_key:
        raise AuthenticationError("Invalid API key.")
