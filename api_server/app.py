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
from agent_orchestration.tools.registry import ToolRegistry
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


def _build_agent_service(llm_service: LLMService) -> AgentService:
    """Build AgentService with stub backends and default tool registry."""

    class _StubWebSearch:
        async def search(self, query: str, max_results: int = 5):
            return []

    class _StubGmail:
        async def search_messages(self, query: str, max_results: int = 10):
            return []

        async def read_message(self, message_id: str):
            from agent_orchestration.tools.backends import GmailMessage

            return GmailMessage(
                message_id=message_id, subject="", sender="", body="", date=""
            )

        async def send_email(self, to: str, subject: str, body: str, cc=None):
            from agent_orchestration.tools.backends import GmailSendResult

            return GmailSendResult(message_id="stub", status="not_configured")

    class _StubCalendar:
        async def search_events(self, query=None, time_min=None, time_max=None):
            return []

        async def create_event(self, payload):
            from agent_orchestration.tools.backends import CalendarEvent

            return CalendarEvent(
                event_id="stub",
                title=payload.title,
                start=payload.start,
                end=payload.end,
            )

        async def update_event(self, event_id, payload):
            from agent_orchestration.tools.backends import CalendarEvent

            return CalendarEvent(
                event_id=event_id,
                title=payload.title or "",
                start=payload.start or "",
                end=payload.end or "",
            )

        async def delete_event(self, event_id):
            from agent_orchestration.tools.backends import CalendarDeleteResult

            return CalendarDeleteResult(event_id=event_id, status="not_configured")

    web_backend = _StubWebSearch()
    gmail_backend = _StubGmail()
    calendar_backend = _StubCalendar()

    registry = ToolRegistry()
    registry.register(WebSearchTool(web_backend))
    registry.register(GmailSearchMessagesTool(gmail_backend))
    registry.register(GmailReadMessageTool(gmail_backend))
    registry.register(GmailSendEmailTool(gmail_backend))
    registry.register(CalendarSearchEventsTool(calendar_backend))
    registry.register(CalendarCreateEventTool(calendar_backend))
    registry.register(CalendarUpdateEventTool(calendar_backend))
    registry.register(CalendarDeleteEventTool(calendar_backend))

    return AgentService(
        llm_service=llm_service,
        registry=registry,
        approval_store=ApprovalStore(),
        checkpoint_store=CheckpointStore(),
        config=AgentConfig(),
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
