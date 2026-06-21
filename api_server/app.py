import logging

from fastapi import FastAPI

from agent_orchestration.approval.store import ApprovalStore
from agent_orchestration.config import AgentConfig
from agent_orchestration.persistence.checkpoint_store import CheckpointStore
from agent_orchestration.service import AgentService
from agent_orchestration.tools.calendar import (
    CalendarCreateEventTool,
    CalendarDeleteEventTool,
    CalendarSearchEventsTool,
    CalendarUpdateEventTool,
)
from agent_orchestration.tools.gmail import (
    GmailReadMessageTool,
    GmailSearchMessagesTool,
    GmailSendEmailTool,
)
from agent_orchestration.tools.backends_stub import (
    StubCalendarBackend,
    StubGmailBackend,
    StubWebFetchBackend,
    StubWebSearchBackend,
)
from agent_orchestration.tools.registry import ToolRegistry
from agent_orchestration.tools.web_fetch import WebFetchTool
from agent_orchestration.tools.web_search import WebSearchTool
from api_server.config import APIServerConfig
from api_server.errors import register_exception_handlers
from api_server.logging import configure_logging
from api_server.routes.chat import router as chat_router
from api_server.routes.health import router as health_router
from api_server.routes.models import router as models_router
from llm.config import LLMConfig
from llm.service import LLMService

logger = logging.getLogger(__name__)


def _build_tool_registry(agent_config: AgentConfig) -> ToolRegistry:
    """Build the tool registry for the configured backend set.

    Only the "stub" backend set is implemented today; real Web/Gmail/Calendar
    backends are a separate feature.
    """
    if agent_config.agent_backend != "stub":
        raise ValueError(
            f"Unsupported agent_backend {agent_config.agent_backend!r}; "
            "only 'stub' is implemented."
        )

    web_backend = StubWebSearchBackend()
    web_fetch_backend = StubWebFetchBackend()
    gmail_backend = StubGmailBackend()
    calendar_backend = StubCalendarBackend()

    registry = ToolRegistry()
    registry.register(WebSearchTool(web_backend))
    registry.register(WebFetchTool(web_fetch_backend))
    registry.register(GmailSearchMessagesTool(gmail_backend))
    registry.register(GmailReadMessageTool(gmail_backend))
    registry.register(GmailSendEmailTool(gmail_backend))
    registry.register(CalendarSearchEventsTool(calendar_backend))
    registry.register(CalendarCreateEventTool(calendar_backend))
    registry.register(CalendarUpdateEventTool(calendar_backend))
    registry.register(CalendarDeleteEventTool(calendar_backend))
    return registry


def _build_agent_service(llm_service: LLMService) -> AgentService:
    """Build AgentService with the configured tool backend set."""
    agent_config = AgentConfig()
    return AgentService(
        llm_service=llm_service,
        registry=_build_tool_registry(agent_config),
        approval_store=ApprovalStore(),
        checkpoint_store=CheckpointStore(),
        config=agent_config,
    )


def create_app(
    config: APIServerConfig | None = None,
    llm_service: LLMService | None = None,
    agent_service: AgentService | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Pass ``config``, ``llm_service``, and ``agent_service`` to override defaults (useful in tests).
    """
    resolved_config = config or APIServerConfig()
    configure_logging(resolved_config.log_level)

    resolved_llm = llm_service or LLMService(LLMConfig())

    app = FastAPI(title="Jarvis API")
    app.state.config = resolved_config
    app.state.llm_service = resolved_llm

    if resolved_config.enable_agent_orchestration:
        app.state.agent_service = agent_service or _build_agent_service(resolved_llm)
        logger.info("Agent orchestration enabled.")
    else:
        app.state.agent_service = None

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
