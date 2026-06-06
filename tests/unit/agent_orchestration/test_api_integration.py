"""API server integration tests: agent routing, LLM passthrough, streaming rejection."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from agent_orchestration.models import AgentResponse
from agent_orchestration.service import AgentService
from api_server.app import create_app
from api_server.config import APIServerConfig
from llm.models import ChatResponse
from llm.service import LLMService


def _mock_llm(content: str = "hello") -> MagicMock:
    llm = MagicMock(spec=LLMService)
    llm.achat = AsyncMock(
        return_value=ChatResponse(content=content, finish_reason="stop")
    )
    return llm


def _mock_agent(content: str = "agent answer") -> MagicMock:
    agent = MagicMock(spec=AgentService)
    agent.achat = AsyncMock(return_value=AgentResponse(content=content))
    return agent


def _body(stream: bool = False) -> dict:
    return {
        "model": "test-model",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": stream,
    }


# ---------------------------------------------------------------------------
# Agent enabled
# ---------------------------------------------------------------------------


def test_routes_to_agent_service_when_enabled():
    config = APIServerConfig(enable_agent_orchestration=True)
    llm = _mock_llm()
    agent = _mock_agent("from agent")
    app = create_app(config=config, llm_service=llm, agent_service=agent)

    with TestClient(app) as client:
        resp = client.post("/v1/chat/completions", json=_body())
    assert resp.status_code == 200
    agent.achat.assert_called_once()
    llm.achat.assert_not_called()
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "from agent"


def test_stream_true_with_agent_returns_unsupported_error():
    config = APIServerConfig(enable_agent_orchestration=True)
    llm = _mock_llm()
    agent = _mock_agent()
    app = create_app(config=config, llm_service=llm, agent_service=agent)

    with TestClient(app) as client:
        resp = client.post("/v1/chat/completions", json=_body(stream=True))
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "unsupported_feature"
    agent.achat.assert_not_called()


# ---------------------------------------------------------------------------
# Agent disabled
# ---------------------------------------------------------------------------


def test_routes_to_llm_service_when_agent_disabled():
    config = APIServerConfig(enable_agent_orchestration=False)
    llm = _mock_llm("from llm")
    app = create_app(config=config, llm_service=llm, agent_service=None)

    with TestClient(app) as client:
        resp = client.post("/v1/chat/completions", json=_body())
    assert resp.status_code == 200
    llm.achat.assert_called_once()
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "from llm"


def test_stream_works_normally_when_agent_disabled():
    config = APIServerConfig(enable_agent_orchestration=False)

    async def _stream_gen(messages, **kwargs):
        from llm.models import LLMStreamChunk

        yield LLMStreamChunk(content="chunk", done=False)
        yield LLMStreamChunk(content="", done=True, finish_reason="stop")

    llm = MagicMock(spec=LLMService)
    llm.stream_chat = _stream_gen
    app = create_app(config=config, llm_service=llm, agent_service=None)

    with TestClient(app) as client:
        resp = client.post("/v1/chat/completions", json=_body(stream=True))
    assert resp.status_code == 200
