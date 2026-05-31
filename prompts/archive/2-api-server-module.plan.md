# API Server Module – Implementation Plan

## Architecture Summary

1. `api_server/config.py` — Pydantic-settings config (host, port, default_model, api_key, enable_api_key_auth, log_level)
2. `api_server/logging.py` — `configure_logging()` helper; standard Python logging setup
3. `api_server/schemas/` — OpenAI-compatible request/response Pydantic models + error schema
4. `api_server/errors.py` — FastAPI exception handlers; consistent OpenAI-style error responses
5. `api_server/adapters/` — Explicit translation layer: OpenAI ↔ internal `llm` models; no logic in route handlers
6. `api_server/routes/` — Three route files: `health.py`, `models.py`, `chat.py`; async handlers
7. `api_server/dependencies.py` — FastAPI `Depends` providers for config and `LLMService`
8. `api_server/app.py` — `create_app()` factory; registers routes, exception handlers, logging
9. `api_server/__init__.py` — Re-exports `create_app` as the module's public surface
10. `main.py` — Top-level entrypoint: initialises config + logging, creates the FastAPI app, starts uvicorn when run directly

---

## Directory Structure

```text
api_server/
├── __init__.py
├── app.py
├── config.py
├── dependencies.py
├── errors.py
├── logging.py
│
├── routes/
│   ├── __init__.py
│   ├── health.py
│   ├── models.py
│   └── chat.py
│
├── schemas/
│   ├── __init__.py
│   ├── openai.py
│   └── errors.py
│
├── adapters/
│   ├── __init__.py
│   ├── openai_to_llm.py
│   └── llm_to_openai.py

tests/
└── unit/
    ├── api_server/
    │   ├── __init__.py
    │   ├── adapters/
    │   │   ├── __init__.py
    │   │   ├── test_openai_to_llm.py
    │   │   └── test_llm_to_openai.py
    │   ├── routes/
    │   │   ├── __init__.py
    │   │   ├── test_health.py
    │   │   ├── test_models.py
    │   │   └── test_chat.py
    │   └── test_errors.py
    └── main/
        ├── __init__.py
        └── test_main.py
```

---

## Planning Questions

### [Question 1]
The `/v1/models` endpoint must return available models. The `llm` module does not expose model listing — it only provides `chat`/`achat`/`generate`/`agenerate`.

Options:

- **A (extend llm module)** — Add `list_models()` / `alist_models()` to `LLMService` and `BaseProvider`. This modifies the `llm` module's public API and is the most complete solution.
- **B (static config)** — Return only the `default_model` value(s) from `APIServerConfig`. Simple, zero changes to `llm`. Suitable if Open WebUI just needs to see one selectable model.
- **C (config list)** — Add a `models: list[str]` field to `APIServerConfig` so multiple models can be declared without touching `llm`. More flexible than B without changing `llm`.

Which option should be used?

## [Answer 1] Follow option A

---

### [Question 2]
The `llm` module's structured output support uses `response_model: type[BaseModel]`, which requires a Python Pydantic class at call time. OpenAI's `response_format` field arrives as JSON:

```json
{ "type": "json_schema", "json_schema": { "name": "...", "schema": {...} } }
```

There is no clean way to dynamically create a `type[BaseModel]` from an incoming JSON schema without additional dependencies (e.g., `datamodel-code-generator`).

Options:

- **A (text only)** — Support `{"type": "text"}` (or omitted). Reject `json_object` and `json_schema` with a `400 unsupported_feature` error. Clean, honest, no hidden behaviour. Streaming has precedent for this pattern.
- **B (json_object passthrough)** — Support `{"type": "json_object"}` by calling the `llm` module without a `response_model` and relying on the model to return valid JSON. No schema validation. Reject `json_schema`.
- **C (ignore silently)** — Accept any `response_format` value but always call `llm` as plain text. Risky: Open WebUI may rely on the format being respected.

Which option should be used?

## [Answer 2] Follow option A

---

### [Question 3]
The config includes `enable_api_key_auth` and `api_key`. Should authentication default to **disabled** (`enable_api_key_auth=False`), with the route returning `401` only when it is explicitly enabled and the key is missing or wrong?

## [Answer 3] Yes, disable it by default. In additional, all the sensitive information, like keys, secrets, ... should be optional and could be injected from env variables

---

### [Question 4]
OpenAI clients often send fields that are not listed in the spec (e.g. `stream_options`, `user`, `seed`, `logprobs`, `n`). Should unknown request fields be:

- **A (ignored)** — Use `model_config = ConfigDict(extra="ignore")` on Pydantic request schemas. Safe and forward-compatible.
- **B (rejected)** — Use `extra="forbid"`. Stricter; may break Open WebUI if it sends non-essential fields.

Which option should be used?

## [Answer 4] Follow option A

---

### [Question 5]
`main.py` is described as "the official application entrypoint" that future agents, automation tools, and deployment systems will use. Two interpretations:

- **A (API-only entrypoint)** — `main.py` starts only the API server. Other future systems (memory, RAG, agents) would import from their own modules and not be wired through `main.py`.
- **B (platform bootstrap entrypoint)** — `main.py` is the future root bootstrap for the entire AI platform. It currently starts the API server, but its structure should anticipate initialising memory, RAG, and agents later.

Which interpretation is correct?

## [Answer 5] Option A is preferred

---

## Implementation Steps

> Steps below will only be executed after all planning questions are answered and the plan is approved.

- [x] **Step 1 – Dependencies**: Add `fastapi`, `uvicorn[standard]`, and `httpx` to `pyproject.toml` via `uv add`
- [x] **Step 2 – Config**: Implement `api_server/config.py` (`APIServerConfig` using pydantic-settings)
- [x] **Step 3 – Logging**: Implement `api_server/logging.py` (`configure_logging()`)
- [x] **Step 4 – Error schemas**: Implement `api_server/schemas/errors.py` (OpenAI error envelope)
- [x] **Step 5 – OpenAI schemas**: Implement `api_server/schemas/openai.py` (request + response models for chat completions and models list)
- [x] **Step 6 – Errors module**: Implement `api_server/errors.py` (FastAPI exception handlers; map LLM exceptions → OpenAI error responses)
- [x] **Step 7 – Adapter: OpenAI → LLM**: Implement `api_server/adapters/openai_to_llm.py` (messages, roles, tools, generation params)
- [x] **Step 8 – Adapter: LLM → OpenAI**: Implement `api_server/adapters/llm_to_openai.py` (chat response, tool calls, finish reason)
- [x] **Step 9 – Health route**: Implement `api_server/routes/health.py`
- [x] **Step 10 – Models route**: Implement `api_server/routes/models.py` (per answer to Question 1); also extended `llm` module with `list_models`/`alist_models`
- [x] **Step 11 – Chat route**: Implement `api_server/routes/chat.py` (stream rejection, adapter invocation, LLM call)
- [x] **Step 12 – Dependencies**: Implement `api_server/dependencies.py` (FastAPI `Depends` for config, LLMService)
- [x] **Step 13 – App factory**: Implement `api_server/app.py` (`create_app()`)
- [x] **Step 14 – Module init**: Update `api_server/__init__.py` to export `create_app`
- [x] **Step 15 – Entrypoint**: Update `main.py` (initialise config + logging, create app, start server when run directly)
- [x] **Step 16 – Test scaffolding**: Create `tests/unit/api_server/` and `tests/unit/main/` directory structure with `__init__.py` files
- [x] **Step 17 – Adapter tests**: Write unit tests for `openai_to_llm` and `llm_to_openai` adapters (message conversion, role conversion, tool schema conversion, tool call conversion, generation params, finish reason)
- [x] **Step 18 – Route tests**: Write unit tests for health, models, and chat routes (stream rejection, error mapping, mock LLMService)
- [x] **Step 19 – Error handler tests**: Write unit tests for error mapping (validation error, unsupported feature, LLM failure, auth failure)
- [x] **Step 20 – Main unit tests**: Write `tests/unit/main/test_main.py` (app factory creation, FastAPI app exposure, importing does not start server, config init, logging init, route registration)
- [x] **Step 21 – Integration tests**: Write integration tests verifying `main.py → api_server` wiring (health, models, chat endpoints exist; mock llm module)
- [x] **Step 22 – Run tests**: Execute full test suite; all tests must pass (132/132)
- [x] **Step 23 – Documentation**: Write `api_server/README.md` and `api_server/DESIGN.md`
