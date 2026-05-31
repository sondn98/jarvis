from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api_server.app import create_app
from api_server.config import APIServerConfig


def _make_client() -> TestClient:
    config = APIServerConfig()
    mock_service = MagicMock()
    app = create_app(config=config, llm_service=mock_service)
    return TestClient(app)


def test_health_returns_ok():
    client = _make_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_does_not_require_auth():
    config = APIServerConfig(enable_api_key_auth=True, api_key="secret")
    mock_service = MagicMock()
    app = create_app(config=config, llm_service=mock_service)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
