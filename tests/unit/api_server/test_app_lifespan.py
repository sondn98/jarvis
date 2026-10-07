from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from api_server.app import create_app
from api_server.config import APIServerConfig


def test_startup_warms_up_agent_service():
    """Entering the app lifespan (startup) eagerly runs MCP discovery."""
    config = APIServerConfig(enable_agent_orchestration=True)
    agent_service = MagicMock()
    agent_service.warmup = AsyncMock()

    app = create_app(
        config=config, llm_service=MagicMock(), agent_service=agent_service
    )

    agent_service.warmup.assert_not_awaited()  # not until startup fires
    with TestClient(app):
        pass  # entering/exiting the context fires the lifespan startup/shutdown

    agent_service.warmup.assert_awaited_once()


def test_startup_without_agent_orchestration_is_noop():
    config = APIServerConfig(enable_agent_orchestration=False)
    app = create_app(config=config, llm_service=MagicMock())
    with TestClient(app):
        pass
    assert app.state.agent_service is None
