from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_server.errors import (
    AuthenticationError,
    UnsupportedFeatureError,
    register_exception_handlers,
)
from llm.exceptions import LLMError, ProviderError, TimeoutError


def _app_with_route(exc_to_raise, raise_server_exceptions: bool = True):
    """Create a minimal FastAPI app that raises the given exception on GET /test."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/test")
    async def trigger():
        raise exc_to_raise

    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_unsupported_feature_returns_400():
    client = _app_with_route(UnsupportedFeatureError("not implemented"))
    resp = client.get("/test")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["type"] == "unsupported_feature"
    assert "not implemented" in body["error"]["message"]


def test_authentication_error_returns_401():
    client = _app_with_route(AuthenticationError("bad key"))
    resp = client.get("/test")
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "authentication_error"


def test_provider_error_returns_502():
    client = _app_with_route(ProviderError("ollama down"))
    resp = client.get("/test")
    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "provider_error"


def test_timeout_error_returns_504():
    client = _app_with_route(TimeoutError("timed out"))
    resp = client.get("/test")
    assert resp.status_code == 504
    assert resp.json()["error"]["type"] == "timeout_error"


def test_llm_error_returns_500():
    client = _app_with_route(LLMError("some llm error"))
    resp = client.get("/test")
    assert resp.status_code == 500
    assert resp.json()["error"]["type"] == "llm_error"


def test_generic_exception_returns_500():
    # raise_server_exceptions=False needed: generic Exception goes through
    # ServerErrorMiddleware which re-raises in test mode by default.
    client = _app_with_route(RuntimeError("unexpected"), raise_server_exceptions=False)
    resp = client.get("/test")
    assert resp.status_code == 500
    assert resp.json()["error"]["type"] == "internal_error"


def test_error_response_never_exposes_stack_trace():
    client = _app_with_route(
        RuntimeError("secret internals"), raise_server_exceptions=False
    )
    resp = client.get("/test")
    body = resp.text
    assert "Traceback" not in body
    assert "secret internals" not in body


def test_error_response_shape():
    client = _app_with_route(UnsupportedFeatureError("x"))
    resp = client.get("/test")
    body = resp.json()
    assert "error" in body
    assert "message" in body["error"]
    assert "type" in body["error"]
    assert "param" in body["error"]
    assert "code" in body["error"]
