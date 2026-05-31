from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api_server.app import create_app
from api_server.config import APIServerConfig
from llm.exceptions import LLMError, ProviderError
from llm.models import ChatResponse, ToolCall


def _make_client(
    llm_response: ChatResponse | None = None,
    llm_side_effect=None,
    enable_auth: bool = False,
    api_key: str | None = None,
):
    config = APIServerConfig(enable_api_key_auth=enable_auth, api_key=api_key)
    mock_service = MagicMock()
    if llm_side_effect is not None:
        mock_service.achat = AsyncMock(side_effect=llm_side_effect)
    else:
        response = llm_response or ChatResponse(content="Hello", finish_reason="stop")
        mock_service.achat = AsyncMock(return_value=response)
    app = create_app(config=config, llm_service=mock_service)
    return TestClient(app)


def _chat_payload(**overrides) -> dict:
    base = {
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    base.update(overrides)
    return base


class TestChatCompletions:
    def test_basic_chat_returns_openai_format(self):
        client = _make_client()
        resp = client.post("/v1/chat/completions", json=_chat_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "chat.completion"
        assert body["model"] == "llama3.2"
        assert len(body["choices"]) == 1
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert body["choices"][0]["message"]["content"] == "Hello"
        assert body["choices"][0]["finish_reason"] == "stop"

    def test_tool_call_response_is_converted(self):
        llm_resp = ChatResponse(
            tool_calls=[ToolCall(id="tc1", name="search", arguments={"query": "test"})],
            finish_reason="tool_calls",
        )
        client = _make_client(llm_response=llm_resp)
        resp = client.post("/v1/chat/completions", json=_chat_payload(tools=[{
            "type": "function",
            "function": {"name": "search", "description": "Search", "parameters": {}},
        }]))
        assert resp.status_code == 200
        choices = resp.json()["choices"]
        assert choices[0]["finish_reason"] == "tool_calls"
        tool_calls = choices[0]["message"]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "tc1"
        assert tool_calls[0]["function"]["name"] == "search"

    def test_generation_params_passed_to_llm(self):
        config = APIServerConfig()
        mock_service = MagicMock()
        mock_service.achat = AsyncMock(return_value=ChatResponse(content="ok", finish_reason="stop"))
        app = create_app(config=config, llm_service=mock_service)
        client = TestClient(app)
        client.post(
            "/v1/chat/completions",
            json=_chat_payload(temperature=0.3, top_p=0.7, max_tokens=100),
        )
        call_kwargs = mock_service.achat.call_args.kwargs
        assert call_kwargs.get("temperature") == 0.3
        assert call_kwargs.get("top_p") == 0.7
        assert call_kwargs.get("max_tokens") == 100


class TestStreamRejection:
    def test_stream_true_returns_400(self):
        client = _make_client()
        resp = client.post("/v1/chat/completions", json=_chat_payload(stream=True))
        assert resp.status_code == 400
        assert resp.json()["error"]["type"] == "unsupported_feature"
        assert "Streaming" in resp.json()["error"]["message"]

    def test_stream_false_is_accepted(self):
        client = _make_client()
        resp = client.post("/v1/chat/completions", json=_chat_payload(stream=False))
        assert resp.status_code == 200


class TestResponseFormat:
    def test_text_format_is_accepted(self):
        client = _make_client()
        resp = client.post(
            "/v1/chat/completions",
            json=_chat_payload(response_format={"type": "text"}),
        )
        assert resp.status_code == 200

    def test_json_object_format_returns_400(self):
        client = _make_client()
        resp = client.post(
            "/v1/chat/completions",
            json=_chat_payload(response_format={"type": "json_object"}),
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["type"] == "unsupported_feature"

    def test_json_schema_format_returns_400(self):
        client = _make_client()
        resp = client.post(
            "/v1/chat/completions",
            json=_chat_payload(response_format={"type": "json_schema"}),
        )
        assert resp.status_code == 400


class TestErrorMapping:
    def test_provider_error_returns_502(self):
        client = _make_client(llm_side_effect=ProviderError("Ollama down"))
        resp = client.post("/v1/chat/completions", json=_chat_payload())
        assert resp.status_code == 502
        assert resp.json()["error"]["type"] == "provider_error"

    def test_llm_error_returns_500(self):
        client = _make_client(llm_side_effect=LLMError("Generic LLM error"))
        resp = client.post("/v1/chat/completions", json=_chat_payload())
        assert resp.status_code == 500

    def test_unknown_fields_are_ignored(self):
        client = _make_client()
        payload = _chat_payload()
        payload["unknown_field"] = "ignored"
        payload["seed"] = 42
        resp = client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 200


class TestAuthentication:
    def test_missing_auth_returns_401(self):
        client = _make_client(enable_auth=True, api_key="secret")
        resp = client.post("/v1/chat/completions", json=_chat_payload())
        assert resp.status_code == 401
        assert resp.json()["error"]["type"] == "authentication_error"

    def test_wrong_key_returns_401(self):
        client = _make_client(enable_auth=True, api_key="secret")
        resp = client.post(
            "/v1/chat/completions",
            json=_chat_payload(),
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401

    def test_correct_key_passes(self):
        client = _make_client(enable_auth=True, api_key="secret")
        resp = client.post(
            "/v1/chat/completions",
            json=_chat_payload(),
            headers={"Authorization": "Bearer secret"},
        )
        assert resp.status_code == 200

    def test_auth_disabled_by_default(self):
        client = _make_client(enable_auth=False)
        resp = client.post("/v1/chat/completions", json=_chat_payload())
        assert resp.status_code == 200
