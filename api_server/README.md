# api_server

OpenAI-compatible HTTP API server for Jarvis. Sits above the `llm` module and exposes an interface that Open WebUI can connect to directly.

## Purpose

Translate OpenAI-style HTTP requests into internal `llm` module calls, and translate responses back into OpenAI-compatible format.

## Features

- `GET /health` — liveness check
- `GET /v1/models` — lists models available on the configured Ollama instance
- `POST /v1/chat/completions` — chat completion with tool-calling support
- Optional API key authentication
- Consistent OpenAI-style JSON error responses
- Structured request/response validation via Pydantic

## Public API

### Factory

```python
from api_server import create_app

app = create_app()                          # uses env-var config
app = create_app(config=cfg, llm_service=svc)  # override for tests
```

### Configuration (`APIServerConfig`)

| Field | Env var | Default | Notes |
|---|---|---|---|
| `host` | `HOST` | `0.0.0.0` | |
| `port` | `PORT` | `8000` | |
| `default_model` | `DEFAULT_MODEL` | `None` | Falls back to `LLMConfig.default_model` |
| `api_key` | `API_KEY` | `None` | |
| `enable_api_key_auth` | `ENABLE_API_KEY_AUTH` | `False` | |
| `log_level` | `LOG_LEVEL` | `INFO` | |

## Usage Examples

### Start the server

```bash
DEFAULT_MODEL=llama3.2 python main.py
```

### Chat completion request

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### With API key auth enabled

```bash
API_KEY=mysecret ENABLE_API_KEY_AUTH=true DEFAULT_MODEL=llama3.2 python main.py

curl -H "Authorization: Bearer mysecret" http://localhost:8000/v1/models
```

## Extension Guide

- **Add streaming**: implement a streaming adapter in `adapters/` and add the streaming path in `routes/chat.py`.
- **Add new endpoints**: create a new file in `routes/`, register it in `app.py`.
- **Add new error types**: register a new handler in `errors.py`; existing error shape is defined in `schemas/errors.py`.
- **Add middleware**: add middleware in `app.py` inside `create_app()`.
