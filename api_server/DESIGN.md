# api_server – Design Document

## Summary

`api_server` is a FastAPI application that exposes an OpenAI-compatible HTTP API on top of the `llm` module. It was designed so Open WebUI can connect to Jarvis using the standard OpenAI client protocol.

**What is implemented:**

- `GET /health` — returns `{"status": "ok"}`
- `GET /v1/models` — calls `LLMService.alist_models()` and returns an OpenAI `ModelListResponse`
- `POST /v1/chat/completions` — accepts OpenAI chat completion requests; routes to `LLMService.achat()` for non-streaming requests and `LLMService.stream_chat()` for streaming requests (`"stream": true`); converts responses into OpenAI format
- Optional Bearer token authentication enforced by a FastAPI dependency
- Consistent OpenAI-style JSON error envelope for all error paths
- Explicit adapter layer: `openai_to_llm` and `llm_to_openai` translate between OpenAI schemas and internal `llm` models
- Application factory `create_app()` accepts optional injected config and service (enables clean testing without environment variables)
- `main.py` is the single application entrypoint; it calls `create_app()` at module level so `from main import app` works

**Main classes / components:**

| Component | File | Responsibility |
|---|---|---|
| `APIServerConfig` | `config.py` | Pydantic-settings config loaded from env |
| `configure_logging` | `logging.py` | Sets up Python root logger |
| `register_exception_handlers` | `errors.py` | Maps LLM/app exceptions to OpenAI error JSON |
| OpenAI schemas | `schemas/openai.py` | Request and response Pydantic models |
| Error schema | `schemas/errors.py` | `OpenAIErrorResponse` envelope |
| `openai_to_llm` | `adapters/openai_to_llm.py` | Converts OpenAI requests → internal models |
| `llm_to_openai` | `adapters/llm_to_openai.py` | Converts internal responses → OpenAI models (batch and streaming) |
| `health` router | `routes/health.py` | `GET /health` |
| `models` router | `routes/models.py` | `GET /v1/models` |
| `chat` router | `routes/chat.py` | `POST /v1/chat/completions` |
| `create_app` | `app.py` | Application factory |

**Known limitations:**

- `response_format` types other than `"text"` are not supported. `json_object` and `json_schema` return `400 unsupported_feature`.
- Multi-turn conversations with assistant messages containing `tool_calls` in the history lose the tool-call context when converted to `llm.Message` (which only has `role` and `content`).

---

## Problem Statement

Open WebUI expects an OpenAI-compatible API. The `llm` module uses an internal model format. A translation layer is needed between the two.

---

## Goals

- Expose `/health`, `/v1/models`, `/v1/chat/completions`
- Translate OpenAI requests ↔ internal `llm` models
- Never call Ollama directly; always go through `LLMService`
- Optional authentication
- Consistent error format

## Non-Goals

- RAG, memory, conversation persistence
- Tool execution
- Embeddings
- Retries
- LangGraph / LangChain integration
- User management

---

## Architecture Overview

```
Open WebUI
    ↓ OpenAI HTTP
api_server
    routes/     ← HTTP handlers (thin, no logic)
    adapters/   ← Translation between OpenAI and internal models
    schemas/    ← Pydantic request/response models
    errors.py   ← Exception handlers
    dependencies.py ← FastAPI Depends providers
    ↓ llm.Message / llm.ToolDefinition
llm
    ↓ Ollama SDK
Ollama
```

Request flow for `POST /v1/chat/completions` (non-streaming):

```
1. FastAPI validates ChatCompletionRequest
2. verify_api_key dependency runs (if enabled)
3. chat route: rejects unsupported response_format
4. openai_to_llm.convert_messages() → list[Message]
5. openai_to_llm.convert_tools() → list[ToolDefinition]
6. openai_to_llm.build_llm_kwargs() → dict (model, temperature, etc.)
7. LLMService.achat(messages, tools=tools, **kwargs)
8. llm_to_openai.convert_chat_response() → ChatCompletionResponse
9. FastAPI serialises response
```

Request flow for `POST /v1/chat/completions` (streaming, `"stream": true`):

```
1. FastAPI validates ChatCompletionRequest
2. verify_api_key dependency runs (if enabled)
3. chat route: detects stream=True, generates request_id
4. Returns StreamingResponse(media_type="text/event-stream")
5. _sse_generator async generator runs:
   a. openai_to_llm.convert_messages() + convert_tools()
   b. LLMService.stream_chat(messages, tools=tools, **kwargs)
   c. For each LLMStreamChunk: llm_to_openai.convert_stream_chunk() → ChatCompletionChunk
   d. Yields "data: {json}\n\n" per chunk
   e. Yields "data: [DONE]\n\n" at end
6. Client receives incremental SSE events
```

---

## Design Decisions

### Adapter layer separated from routes

Translation logic lives in `adapters/`, not in route handlers. Routes are kept to 10–15 lines. This makes the adapters independently testable and keeps the routes readable.

### App factory pattern with injectable dependencies

`create_app(config, llm_service)` accepts optional overrides. This means tests can pass mock objects without patching env vars or module-level state. `main.py` calls `create_app()` with no arguments for production use.

### Exception handler for `Exception`

A catch-all handler ensures no raw stack traces reach clients. In Starlette's test client, `RuntimeError` (and other non-framework exceptions) still re-raises in `raise_server_exceptions=True` mode because they go through `ServerErrorMiddleware`. Tests for the generic handler use `raise_server_exceptions=False`.

### `response_format` rejected unless `"text"`

The `llm` module's structured output requires a Python `type[BaseModel]`. There is no practical way to build a Pydantic class from an incoming JSON schema at request time. `json_object` and `json_schema` are rejected explicitly rather than silently ignored.

### Streaming via SSE, not buffered

When `stream=true`, the route returns `StreamingResponse(media_type="text/event-stream")` backed by an async generator that iterates `LLMService.stream_chat()`. Each `LLMStreamChunk` is converted to a `ChatCompletionChunk` (OpenAI `chat.completion.chunk` format) and forwarded immediately as `data: {json}\n\n`. The stream terminates with `data: [DONE]\n\n`.

This means HTTP 200 is committed before any chunks arrive. If the provider fails mid-stream, the client receives a truncated SSE stream rather than an HTTP error code — consistent with how production LLM APIs behave.

---

## Public Contracts

### Endpoints

| Method | Path | Auth? | Notes |
|---|---|---|---|
| GET | `/health` | No | Always returns `{"status": "ok"}` |
| GET | `/v1/models` | Optional | Returns `ModelListResponse` |
| POST | `/v1/chat/completions` | Optional | Returns `ChatCompletionResponse` (non-streaming) or SSE stream of `ChatCompletionChunk` (streaming) |

### Error envelope

All errors use:
```json
{
  "error": {
    "message": "Human readable message",
    "type": "error_type",
    "param": null,
    "code": null
  }
}
```

| Exception | HTTP Status | type |
|---|---|---|
| `RequestValidationError` | 422 | `invalid_request_error` |
| `UnsupportedFeatureError` | 400 | `unsupported_feature` |
| `AuthenticationError` | 401 | `authentication_error` |
| `ProviderError` | 502 | `provider_error` |
| `TimeoutError` | 504 | `timeout_error` |
| `LLMError` | 500 | `llm_error` |
| `Exception` | 500 | `internal_error` |

---

## Extension Points

- **New endpoints**: add route file in `routes/`, register in `app.py`
- **New error types**: add handler in `errors.py`
- **Middleware (CORS, rate-limiting)**: add in `create_app()` in `app.py`
- **response_format support**: when `llm` gains a dynamic-schema capability, add the mapping in `adapters/openai_to_llm.py`

---

## Current Implementation Status

- [x] `GET /health`
- [x] `GET /v1/models` (via `LLMService.alist_models`)
- [x] `POST /v1/chat/completions`
- [x] Tool calling (first-class: accepted, passed to llm, returned in OpenAI format)
- [x] Optional API key authentication
- [x] OpenAI error envelope
- [x] Adapter layer
- [x] Application factory
- [x] `main.py` entrypoint
- [x] Streaming (`stream=true` → SSE via `LLMService.stream_chat`)
- [ ] `response_format: json_object` / `json_schema`
- [ ] Multi-turn tool-call history (lossless)

---

## Testing Strategy

All tests are in `tests/unit/api_server/` and `tests/unit/main/`.

- **Adapter tests**: pure unit tests; no HTTP, no mocks needed
- **Route tests**: use `fastapi.testclient.TestClient` with a mocked `LLMService`; no Ollama required
- **Error handler tests**: use a minimal FastAPI app with a route that raises; verify HTTP status and JSON shape
- **Main tests**: use `importlib.reload` with `patch("api_server.app.LLMService")` to test `main.py` behaviour without env vars or Ollama

---

## Known Limitations

1. `response_format` only supports `"text"`
3. Assistant messages with `tool_calls` in conversation history lose call context (llm.Message has no `tool_calls` field)
4. `TestClient` re-raises generic `RuntimeError` in `raise_server_exceptions=True` mode — tests for the catch-all handler use `raise_server_exceptions=False`

---

## Future Roadmap

- Support `response_format: json_object` (after `llm` module adds schema-less JSON mode)
- Extend `llm.Message` to carry `tool_calls` for lossless multi-turn history
- Add CORS middleware for browser-based clients
