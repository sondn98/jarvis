import logging

from fastapi import FastAPI

from api_server.config import APIServerConfig
from api_server.errors import register_exception_handlers
from api_server.logging import configure_logging
from api_server.routes.chat import router as chat_router
from api_server.routes.health import router as health_router
from api_server.routes.models import router as models_router
from llm.config import LLMConfig
from llm.service import LLMService

logger = logging.getLogger(__name__)


def create_app(
    config: APIServerConfig | None = None,
    llm_service: LLMService | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Pass ``config`` and ``llm_service`` to override defaults (useful in tests).
    """
    resolved_config = config or APIServerConfig()
    configure_logging(resolved_config.log_level)

    resolved_service = llm_service or LLMService(LLMConfig())

    app = FastAPI(title="Jarvis API")
    app.state.config = resolved_config
    app.state.llm_service = resolved_service

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(models_router, prefix="/v1")
    app.include_router(chat_router, prefix="/v1")

    logger.info(
        "API server initialised: host=%s port=%s",
        resolved_config.host,
        resolved_config.port,
    )
    return app
