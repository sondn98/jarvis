import logging

from fastapi import FastAPI

from agent_orchestration.approval.store import ApprovalStore
from agent_orchestration.config import AgentConfig
from agent_orchestration.mcp.config import load_mcp_config
from agent_orchestration.mcp.manager import MCPManager
from agent_orchestration.persistence.checkpoint_store import CheckpointStore
from agent_orchestration.service import AgentService
from agent_orchestration.tools.registry import ToolRegistry
from api_server.config import APIServerConfig
from api_server.errors import register_exception_handlers
from api_server.logging import configure_logging
from api_server.routes.chat import router as chat_router
from api_server.routes.health import router as health_router
from api_server.routes.models import router as models_router
from llm.config import LLMConfig
from llm.service import LLMService

logger = logging.getLogger(__name__)


def _build_mcp_manager(agent_config: AgentConfig) -> MCPManager | None:
    """Build the MCP manager from the JSON config file, if one is configured.

    The config file is parsed here at startup; MCP servers themselves are not
    contacted until the first agent request (see MCPManager.ensure_ready).
    """
    if not agent_config.mcp_config_path:
        return None
    mcp_config = load_mcp_config(agent_config.mcp_config_path)
    logger.info(
        "Loaded MCP config from %s: %d server(s) configured.",
        agent_config.mcp_config_path,
        len(mcp_config.servers),
    )
    return MCPManager(mcp_config)


def _build_agent_service(llm_service: LLMService) -> AgentService:
    """Build AgentService.

    Tools are supplied entirely by MCP servers: the registry starts empty and is
    populated lazily on first use from the configured MCP servers (see MCPManager).
    """
    agent_config = AgentConfig()
    return AgentService(
        llm_service=llm_service,
        registry=ToolRegistry(),
        approval_store=ApprovalStore(),
        checkpoint_store=CheckpointStore(),
        config=agent_config,
        mcp_manager=_build_mcp_manager(agent_config),
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
