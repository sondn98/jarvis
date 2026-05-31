import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_server.app import create_app
from api_server.config import APIServerConfig


def _reload_main():
    """Reload main.py with a mocked LLMService so no Ollama connection is needed."""
    sys.modules.pop("main", None)
    mock_service = MagicMock()
    with patch("api_server.app.LLMService", return_value=mock_service):
        main = importlib.import_module("main")
    return main


class TestAppFactory:
    def test_create_app_returns_fastapi_instance(self):
        app = create_app(config=APIServerConfig(), llm_service=MagicMock())
        assert isinstance(app, FastAPI)

    def test_create_app_stores_config_on_state(self):
        config = APIServerConfig(host="127.0.0.1", port=9000)
        app = create_app(config=config, llm_service=MagicMock())
        assert app.state.config is config

    def test_create_app_stores_llm_service_on_state(self):
        service = MagicMock()
        app = create_app(config=APIServerConfig(), llm_service=service)
        assert app.state.llm_service is service

    def test_create_app_accepts_none_and_uses_defaults(self):
        mock_service = MagicMock()
        with patch("api_server.app.LLMService", return_value=mock_service):
            app = create_app()
        assert isinstance(app, FastAPI)


class TestMainEntrypoint:
    def test_app_is_exposed_as_module_attribute(self):
        main = _reload_main()
        assert hasattr(main, "app")
        assert isinstance(main.app, FastAPI)

    def test_importing_does_not_start_server(self):
        """Importing main must not call uvicorn.run."""
        with patch("uvicorn.run") as mock_run:
            _reload_main()
            mock_run.assert_not_called()

    def test_config_initialised_on_app_state(self):
        main = _reload_main()
        assert hasattr(main.app.state, "config")
        assert isinstance(main.app.state.config, APIServerConfig)

    def test_llm_service_initialised_on_app_state(self):
        main = _reload_main()
        assert hasattr(main.app.state, "llm_service")


class TestRouteRegistration:
    def test_health_route_registered(self):
        app = create_app(config=APIServerConfig(), llm_service=MagicMock())
        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_models_route_registered(self):
        app = create_app(config=APIServerConfig(), llm_service=MagicMock())
        routes = [r.path for r in app.routes]
        assert "/v1/models" in routes

    def test_chat_completions_route_registered(self):
        app = create_app(config=APIServerConfig(), llm_service=MagicMock())
        routes = [r.path for r in app.routes]
        assert "/v1/chat/completions" in routes


class TestMainIntegration:
    """Verify main.py → api_server wiring end-to-end using TestClient."""

    def _client(self):
        mock_service = MagicMock()
        mock_service.alist_models = AsyncMock(return_value=["llama3.2"])
        mock_service.achat = AsyncMock(
            return_value=__import__("llm.models", fromlist=["ChatResponse"]).ChatResponse(
                content="ok", finish_reason="stop"
            )
        )
        app = create_app(config=APIServerConfig(), llm_service=mock_service)
        return TestClient(app)

    def test_health_endpoint_works(self):
        client = self._client()
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_models_endpoint_exists(self):
        client = self._client()
        resp = client.get("/v1/models")
        assert resp.status_code == 200

    def test_chat_completions_endpoint_exists(self):
        client = self._client()
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "llama3.2", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200

    def test_openai_compatible_endpoints_present(self):
        app = create_app(config=APIServerConfig(), llm_service=MagicMock())
        client = TestClient(app)
        paths = [r.path for r in app.routes]
        assert "/v1/models" in paths
        assert "/v1/chat/completions" in paths
