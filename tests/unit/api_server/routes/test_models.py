from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from api_server.app import create_app
from api_server.config import APIServerConfig


def _make_client(
    models: list[str] | None = None,
    enable_auth: bool = False,
    api_key: str | None = None,
):
    config = APIServerConfig(enable_api_key_auth=enable_auth, api_key=api_key)
    mock_service = MagicMock()
    mock_service.alist_models = AsyncMock(
        return_value=models if models is not None else ["llama3.2", "mistral"]
    )
    app = create_app(config=config, llm_service=mock_service)
    return TestClient(app)


def test_list_models_returns_openai_format():
    client = _make_client(models=["llama3.2"])
    response = client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == "llama3.2"
    assert body["data"][0]["object"] == "model"
    assert body["data"][0]["owned_by"] == "local"


def test_list_models_returns_all_models():
    client = _make_client(models=["a", "b", "c"])
    response = client.get("/v1/models")
    assert response.status_code == 200
    ids = [m["id"] for m in response.json()["data"]]
    assert ids == ["a", "b", "c"]


def test_list_models_empty():
    client = _make_client(models=[])
    response = client.get("/v1/models")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_list_models_requires_auth_when_enabled():
    client = _make_client(enable_auth=True, api_key="mykey")
    response = client.get("/v1/models")
    assert response.status_code == 401


def test_list_models_passes_with_valid_auth():
    client = _make_client(models=["x"], enable_auth=True, api_key="mykey")
    response = client.get("/v1/models", headers={"Authorization": "Bearer mykey"})
    assert response.status_code == 200
