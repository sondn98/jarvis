# llm — Design Document

## Summary

The `llm` module is the single, centralized access point for all LLM interactions in the Jarvis application. No other module imports provider SDKs directly.

**What is implemented:**

- `LLMService` — the public entry point with four methods: `chat`, `achat`, `generate`, `agenerate`
- `LLMConfig` — Pydantic-settings-based configuration loaded from environment variables with fail-fast validation
- `Message`, `MessageRole`, `ToolDefinition`, `ToolCall`, `ChatResponse` — provider-agnostic Pydantic models that form the canonical message format for the entire application
- `BaseProvider` — a minimal abstract interface isolating the rest of the application from provider-specific code
- `OllamaProvider` — the only concrete provider, backed by the official Ollama Python SDK
- Custom exception hierarchy (`LLMError`, `ConfigurationError`, `ProviderError`, `TimeoutError`, `StructuredOutputError`, `ToolCallParsingError`)
- Tool calling: accepts `ToolDefinition` objects, translates them to Ollama format, parses responses into `ToolCall` objects
- Structured output: accepts a Pydantic `response_model`, passes its JSON schema as the Ollama `format` parameter, validates and returns the result
- 48 unit tests covering config, models, service, and provider layers; all mocked, fast, and deterministic

**Known limitations:**

- Only the Ollama provider is implemented
- No streaming support
- No retry logic — all retry decisions are delegated to callers
- No connection pooling configuration beyond the SDK defaults

**Future extension points:**

- New providers: implement `BaseProvider` and inject via `LLMService(config, provider=...)`
- Streaming: add `stream_chat` / `astream_chat` methods to `BaseProvider`
- Retry: wrap `LLMService` at the call site or add a retry-capable decorator provider

---

## Problem Statement

The application needs to call LLMs in multiple places (agent nodes, planners, tools). Without a centralized module, each call site would directly import and configure provider SDKs, creating tight coupling, duplicated configuration, and inconsistent error handling. The `llm` module solves this by providing one stable, typed interface that hides all provider details.

---

## Goals

- Single access point: no caller imports a provider SDK directly
- Consistent, typed request/response models across all call sites
- Stateless: the module sends requests and returns responses; no conversation history, session state, or memory
- Async-first: all public APIs have async variants for compatibility with LangGraph and concurrent agent workflows
- Fail fast: invalid configuration and provider errors surface immediately as typed exceptions
- Easy to test: provider is injectable, all SDK calls are mockable

---

## Non-Goals

The `llm` module explicitly does not handle:

- Conversation history or session management
- Memory or context window management
- Tool execution (returns `ToolCall` objects; execution belongs to higher layers)
- RAG retrieval
- Agent orchestration or workflow management
- Retry logic
- Streaming responses
- Embedding generation
- Token/usage accounting
- Multi-provider routing or fallback
- LangGraph-specific code (though the API is designed to work naturally within LangGraph nodes)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Caller (agent, node, etc.)        │
└──────────────────────────┬──────────────────────────┘
                           │ chat(messages, tools?, response_model?)
                           ▼
┌─────────────────────────────────────────────────────┐
│                     LLMService                      │
│  chat / achat / generate / agenerate                │
│  - delegates entirely to BaseProvider               │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│                   BaseProvider (ABC)                │
│  chat(messages, tools, response_model) → ChatResponse│
│  achat(...)                                         │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│                  OllamaProvider                     │
│  - translates Message → ollama dict                 │
│  - translates ToolDefinition → ollama tool dict     │
│  - calls ollama.Client / AsyncClient                │
│  - parses ToolCall objects from response            │
│  - validates structured output via Pydantic         │
│  - maps SDK exceptions → internal exceptions        │
└─────────────────────────────────────────────────────┘
```

### Component responsibilities

| Component | Responsibility |
|---|---|
| `LLMConfig` | Load and validate configuration from env vars at startup |
| `LLMService` | Public API surface; owns no logic beyond delegating to the provider |
| `BaseProvider` | Abstract contract ensuring providers are interchangeable |
| `OllamaProvider` | All Ollama-specific translation and SDK interaction |
| Models (`models.py`) | Canonical, provider-agnostic data shapes used across the application |
| Exceptions (`exceptions.py`) | Typed error surface; no raw SDK exceptions escape the provider |

### Data flow — plain chat

```
Caller
  → Message list
  → LLMService.chat()
  → OllamaProvider.chat()
      → _to_ollama_message() per message
      → ollama.Client.chat()
      → _build_chat_response()
  → ChatResponse
  → Caller
```

### Data flow — tool calling

```
Caller
  → messages + ToolDefinition list
  → OllamaProvider
      → _to_ollama_tool() per tool
      → ollama.Client.chat(tools=...)
      → model returns tool_calls
      → _parse_tool_calls() → list[ToolCall]
  → ChatResponse(tool_calls=[...])
  → Caller executes tools
  → Caller sends tool results as Message(role=TOOL, ...)
  → repeat
```

### Data flow — structured output

```
Caller
  → messages + response_model (Pydantic class)
  → OllamaProvider
      → response_model.model_json_schema() → passed as format=
      → ollama.Client.chat(format=schema)
      → model returns JSON string
      → response_model.model_validate_json(content)
      → re-serialized as model_dump_json()
  → ChatResponse(content='{"field": ...}')
  → Caller parses: MyModel.model_validate_json(response.content)
```

---

## Design Decisions

### 1. `LLMService` as a thin delegation layer

**Chosen:** `LLMService` contains no business logic; it only translates `generate` into a single-message `chat` call and delegates everything else to the provider.

**Why:** The service exists to provide a stable public API surface, not to own logic. Keeping it thin means logic stays in the provider where it can be tested in isolation.

**Alternative:** Put structured output parsing and tool-call parsing in the service.

**Tradeoff:** Logic in the provider makes the provider harder to swap, but it keeps provider-specific behavior (e.g. how Ollama structures tool responses) co-located with the Ollama code. This is appropriate since structured output format is inherently provider-specific.

---

### 2. Minimal provider abstraction

**Chosen:** `BaseProvider` exposes only two methods (`chat`, `achat`). No separate method for tool calling or structured output — these are parameters.

**Why:** Separate methods (`chat_with_tools`, `structured_chat`) would fragment the API without adding value. All these behaviors are request variations, not different operations.

**Tradeoff:** The `response_model` and `tools` parameters appear in the base interface even if a provider doesn't support them. A provider that doesn't support tools should raise `ProviderError` — this is acceptable given the current single-provider scope.

---

### 3. `pydantic-settings` for configuration

**Chosen:** `LLMConfig` extends `BaseSettings`, which automatically maps environment variable names to fields.

**Why:** Zero-boilerplate env var loading, `.env` file support, and Pydantic validation in one step.

**Alternative:** Plain `os.environ` lookups in a regular `BaseModel`.

**Tradeoff:** Adds `pydantic-settings` as a dependency. Justified by the elimination of manual env-loading boilerplate.

---

### 4. `ConfigurationError` raised directly from validators (not wrapped in `ValidationError`)

**Chosen:** `field_validator` methods raise `ConfigurationError` directly. Pydantic only wraps `ValueError` / `AssertionError` into `ValidationError`; other exceptions propagate as-is.

**Why:** `ConfigurationError` is more meaningful to callers than `ValidationError`. Callers catching `LLMError` get the right type automatically.

**Tradeoff:** `LLMConfig()` raises `ValidationError` for missing required fields (pydantic's own check) but raises `ConfigurationError` for invalid values. This inconsistency is acceptable because missing required fields are a different class of error (missing env var vs. bad value).

---

### 5. Structured output via Ollama's `format` parameter

**Chosen:** Pass `response_model.model_json_schema()` as the `format` argument to `ollama.Client.chat()`. Ollama constrains generation to valid JSON matching that schema. The response content is then parsed with `model_validate_json`.

**Why:** This is the native Ollama structured output mechanism and requires no post-hoc parsing of free text.

**Tradeoff:** The schema is generated from the Pydantic model at call time (minor overhead). If the model returns malformed JSON despite the format constraint, `StructuredOutputError` is raised immediately — no retries.

---

### 6. No retries

**Chosen:** On any failure, raise the appropriate exception immediately.

**Why:** Retry policy (backoff, jitter, max attempts) is a cross-cutting concern that belongs at the call site or in a separate wrapper, not inside the LLM module. Different callers have different retry requirements.

**Tradeoff:** Callers must implement their own retry logic. This is a deliberate constraint to keep the module simple.

---

## Public Contracts

### `BaseProvider`

```python
class BaseProvider(ABC):
    def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse: ...

    async def achat(...) -> ChatResponse: ...
```

Any new provider must implement both methods and must not raise exceptions outside the `LLMError` hierarchy.

### `ChatResponse`

The stable return type for all public APIs. Callers should never depend on provider-specific response objects.

```python
class ChatResponse(BaseModel):
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str | None
```

When `tool_calls` is non-empty, `content` may be empty. When `response_model` was provided, `content` contains the JSON-serialized validated model.

### `Message`

The canonical message format. All callers construct messages using this model; providers translate it to their own format internally.

---

## Extension Points

### Adding a new provider (e.g. OpenAI, Anthropic)

1. Create `llm/providers/<name>.py`
2. Implement `BaseProvider.chat` and `BaseProvider.achat`
3. Map provider-specific errors to the `LLMError` hierarchy
4. Inject via `LLMService(config, provider=MyProvider(config))`

No changes to `LLMService`, `models.py`, or `exceptions.py` are required.

### Adding streaming

1. Add `stream_chat` / `astream_chat` to `BaseProvider` returning an `AsyncIterator[ChatResponse]`
2. Implement in `OllamaProvider` using `ollama.Client.chat(stream=True)`
3. Add corresponding methods to `LLMService`

Existing non-streaming callers are unaffected.

### Adding a retry wrapper

Implement a `RetryingProvider(BaseProvider)` that wraps any `BaseProvider` and retries on `ProviderError` / `TimeoutError`. Inject it around the real provider:

```python
llm = LLMService(config, provider=RetryingProvider(OllamaProvider(config), max_retries=3))
```

---

## Current Implementation Status

- [x] `LLMConfig` — env var loading with fail-fast validation
- [x] Custom exception hierarchy
- [x] Provider-agnostic Pydantic models (`Message`, `ToolDefinition`, `ToolCall`, `ChatResponse`)
- [x] `BaseProvider` abstract interface
- [x] `OllamaProvider` — sync and async chat
- [x] Tool calling support
- [x] Structured output support
- [x] `LLMService` with `chat`, `achat`, `generate`, `agenerate`
- [x] Unit tests (48 tests, all passing)
- [ ] Streaming support
- [ ] Retry / backoff support
- [ ] Additional providers (OpenAI, Anthropic, etc.)
- [ ] Embedding generation
- [ ] Token / usage accounting
- [ ] Connection pooling configuration

---

## Testing Strategy

### Unit tests

Location: `tests/unit/llm/`

All unit tests mock the Ollama SDK (`ollama.Client`, `ollama.AsyncClient`). Tests are fast, deterministic, and isolated from network state.

| File | What it covers |
|---|---|
| `test_config.py` | Valid config, missing required fields, invalid values |
| `test_models.py` | Model construction, field validation, default values |
| `test_service.py` | Delegation to provider, `generate` → `chat` wrapping, async paths |
| `providers/test_ollama.py` | Message/tool translation, response parsing, error mapping, tool calls, structured output, async |

### Integration tests

Location: `tests/integration/` (not yet implemented)

Integration tests should use a real Ollama instance and cover end-to-end chat, tool calling, and structured output with an actual model.

### Critical test scenarios

- Missing required configuration → `ValidationError`
- Invalid config values (temperature, timeout, etc.) → `ConfigurationError`
- `ProviderError` on `ollama.ResponseError`
- `StructuredOutputError` on malformed JSON or schema mismatch
- `ToolCallParsingError` on malformed tool-call response
- Async paths return identical results to sync paths

---

## Known Limitations

1. **Single provider**: only Ollama is supported. Multi-provider routing or fallback is not implemented.
2. **No streaming**: `stream=False` is always passed to the Ollama SDK. Streaming is a future extension point.
3. **No retries**: the module raises immediately on failure. Callers own retry logic.
4. **Structured output consistency**: Ollama's JSON-constrained generation is best-effort. The module raises `StructuredOutputError` on validation failure rather than attempting repair or retry.
5. **`ConfigurationError` vs `ValidationError`**: missing required env vars raise `ValidationError` (from pydantic); invalid values raise `ConfigurationError`. Callers should catch `(ValidationError, ConfigurationError)` for complete config error handling.
6. **Tool call IDs**: Ollama does not return tool call IDs, so `ToolCall.id` is assigned a generated UUID. Callers must not depend on this ID being stable across equivalent requests.

---

## Future Roadmap

1. **Integration tests** against a real Ollama instance
2. **Streaming API** (`stream_chat` / `astream_chat`)
3. **Retry wrapper provider** for configurable backoff
4. **Additional providers** (OpenAI, Anthropic) via `BaseProvider`
5. **Token usage tracking** — surface `prompt_eval_count` / `eval_count` from Ollama in `ChatResponse`
6. **Timeout via httpx/asyncio** — replace SDK-level timeout with explicit `asyncio.wait_for` for more reliable async cancellation
