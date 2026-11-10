# LiteLLM Provider

## Purpose

The `llm` module is Jarvis's only provider-facing layer. Today it talks to
models exclusively through the Ollama Python SDK (`llm/providers/ollama.py`),
which ties Jarvis to locally hosted Ollama models.

This task **replaces** the Ollama provider with a single `LiteLLMProvider`
backed by the `litellm` SDK, so `DEFAULT_MODEL` can name any model LiteLLM
supports (`gemini/gemini-2.5-flash`, `ollama_chat/llama3.2`,
`openai/gpt-4o-mini`, …) without code changes.

This is a provider swap inside `llm/`. The public surface of the module
(`LLMService`, `BaseProvider`, the models in `llm/models.py`, the exceptions in
`llm/exceptions.py`) does not change. `api_server` and `agent_orchestration`
must not need any code change.

---

# High-Level Goals

* One concrete provider, `LiteLLMProvider`, implementing the existing
  `BaseProvider` contract: `chat`, `achat`, `astream_chat`, `list_models`,
  `alist_models`.
* `LLMService` defaults to `LiteLLMProvider` instead of `OllamaProvider`.
* Remove the Ollama provider, its tests, its config field, and the `ollama`
  dependency.
* Stay provider-neutral: no per-backend branches (`if model.startswith("gemini/")`)
  anywhere in Jarvis code. LiteLLM owns backend differences.

`llm` should **not** become a router, a fallback chain, a cost tracker, or a
wrapper around the LiteLLM Proxy server.

---

# Architectural Principles

Favor:

* Simplicity over abstraction
* Readability over flexibility
* Maintainability over extensibility
* Explicitness over cleverness

Do not add (unless the task explicitly asks for it):

* Plugin systems, middleware, registries, event buses
* Dependency injection frameworks
* Generic framework-style abstractions
* Provider selection settings (`LLM_PROVIDER=...`) — there is one provider

When requirements are ambiguous: do not expand scope, choose the simplest
implementation that satisfies the stated requirements, and document assumptions.

Mirror the structure of the current `ollama.py`: module-level pure translation
helpers (`_to_litellm_message`, `_to_litellm_tool`, `_parse_tool_calls`,
`_build_chat_response`, `_map_error`), and a provider class with shared
`_prepare_request` / `_log_request` / `_log_response` helpers used by both the
sync and async paths.

---

# Repository Structure

```text
llm/
├── __init__.py            # unchanged exports
├── config.py              # ollama_base_url removed; llm_api_base / llm_api_key added
├── exceptions.py          # unchanged
├── models.py              # unchanged
├── service.py             # default provider -> LiteLLMProvider
├── DESIGN.md              # updated
├── README.md              # updated
└── providers/
    ├── __init__.py
    ├── base.py            # unchanged
    └── litellm.py         # NEW — replaces ollama.py
                           # (ollama.py deleted)

tests/
└── unit/
    ├── llm/
    │   ├── test_config.py         # updated for new fields
    │   ├── test_service.py        # default-provider assertion updated if present
    │   └── providers/
    │       └── test_litellm.py    # NEW — replaces test_ollama.py
    └── test_logging/
        └── test_debug_logging.py  # Ollama-provider tests retargeted to LiteLLMProvider
```

Notes:

* Name the module `llm/providers/litellm.py` and import the SDK as
  `import litellm as litellm_sdk` inside it. That matches the `ollama as ollama_sdk`
  convention and keeps the local module name and the SDK name apart.
* Tests live under `tests/`, never inside the implementation package.
* Dependencies: keep the owner's existing pin `litellm[google]==1.108.1`; remove
  `ollama>=0.6.2` via `uv remove ollama`; re-lock with `uv lock`. Keep `httpx`:
  it is a direct dependency used elsewhere.

---

# Configuration

`LLMConfig` stays a `pydantic-settings` `BaseSettings` reading env vars and the
project-root `.env`. No second configuration mechanism.

| Field | Env var | Default | Notes |
|---|---|---|---|
| `default_model` | `DEFAULT_MODEL` | *(required)* | A LiteLLM model string, e.g. `gemini/gemini-2.5-flash`. Existing non-empty validator kept. |
| `llm_api_key` | `LLM_API_KEY` | `None` | `SecretStr \| None`. When set, passed as `api_key=` on every LiteLLM call. |
| `llm_api_base` | `LLM_API_BASE` | `None` | `str \| None`. When set, passed as `api_base=` (e.g. a non-default Ollama host or a self-hosted OpenAI-compatible endpoint). |
| `request_timeout` | `REQUEST_TIMEOUT` | `60.0` | Passed as `timeout=`. Existing validator kept. |
| `default_temperature` / `default_top_p` / `default_max_tokens` | unchanged | unchanged | Mapped to LiteLLM's `temperature` / `top_p` / `max_tokens`. |

Remove `ollama_base_url` / `OLLAMA_BASE_URL`.

Why explicit `LLM_API_KEY` / `LLM_API_BASE` rather than relying only on
LiteLLM's native env vars (`GEMINI_API_KEY`, …): `pydantic-settings` reads `.env`
into `LLMConfig` but does **not** export it to `os.environ`, so a key written only
in `.env` would never reach LiteLLM. Native env vars that are actually exported
in the process environment keep working untouched. Jarvis does not copy them,
validate them, or name them.

Fail fast at startup only on what the existing validators already check. Do not
validate that a model string is known to LiteLLM.

---

# Request Translation

All calls go through `litellm_sdk.completion` (sync) and
`litellm_sdk.acompletion` (async, and streaming with `stream=True`).

```python
# illustrative, not binding
litellm_sdk.acompletion(
    model=model,                       # kwargs.get("model", config.default_model)
    messages=[{"role": m.role.value, "content": m.content} for m in messages],
    tools=[_to_litellm_tool(t) for t in tools] if tools else None,
    response_format=response_model,    # None, or the Pydantic class
    temperature=...,                   # kwargs override, else config default
    top_p=...,
    max_tokens=...,
    timeout=config.request_timeout,
    api_key=config.llm_api_key.get_secret_value() if config.llm_api_key else None,
    api_base=config.llm_api_base,
    drop_params=True,
)
```

* **Tools** use the OpenAI function shape the Ollama helper already builds:
  `{"type": "function", "function": {"name", "description", "parameters"}}`.
* **Structured output**: pass the Pydantic class as `response_format`, then
  validate the returned content with `response_model.model_validate_json` exactly
  as today. A validation failure raises `StructuredOutputError`.
* **`drop_params=True`**: because `DEFAULT_MODEL` can be any backend, sampling
  params a given model rejects (e.g. `top_p` on some reasoning models) are
  dropped by LiteLLM instead of failing the request. This is an assumption.
  Revisit it if silent dropping causes confusion.
* Pass only `None` for `api_key` / `api_base` when they're unset, so LiteLLM falls
  back to its own env-var resolution.

---

# Response Translation

`litellm` returns OpenAI-shaped `ModelResponse` objects. Map
`raw.choices[0]` to `ChatResponse`:

* `content` ← `choice.message.content or None`
* `finish_reason` ← `choice.finish_reason`
* `tool_calls` ← `choice.message.tool_calls`, each mapped to `ToolCall`:
  * `id` ← `tc.id` if present, else `str(uuid4())` (some backends omit ids)
  * `name` ← `tc.function.name`
  * `arguments` ← `json.loads(tc.function.arguments)` when it is a string, or the
    dict as-is. Empty or `None` becomes `{}`. Any parse failure, including
    non-dict JSON, raises `ToolCallParsingError`.

Precedence stays the same as the current provider: a tool-call response returns
immediately. Otherwise, if `response_model` is set, validate. Otherwise return the
plain content.

No LiteLLM types leave `llm/providers/litellm.py`.

---

# Streaming

`astream_chat` calls `acompletion(..., stream=True)` and iterates the async
stream. For each chunk:

```python
LLMStreamChunk(
    content=chunk.choices[0].delta.content or "",
    done=chunk.choices[0].finish_reason is not None,
    provider="litellm",
    model=chunk.model,
    finish_reason=chunk.choices[0].finish_reason,
    raw=None,
)
```

Skip chunks with an empty `choices` list (some backends send a trailing
usage-only chunk). Keep the existing behaviour of ignoring tool-call deltas
during streaming. Keep the existing `Stream started` / `Stream completed` DEBUG
logs and the per-chunk TRACE log.

---

# Model Listing

* `list_models()` returns `litellm_sdk.get_valid_models()` called with no
  arguments, as a `list[str]`.
* `alist_models()` runs the same call with `await asyncio.to_thread(...)`. The
  SDK has no async variant, and blocking the event loop in `GET /v1/models` is not
  acceptable.
* Document this clearly in `llm/README.md`: the result is LiteLLM's inference
  from provider API keys present in the **process environment**. Keys that exist
  only in `.env` / `LLM_API_KEY`, and local Ollama models, are not reflected. An
  empty list is a valid result, not an error.
* Any exception from `get_valid_models` maps to `ProviderError`.

---

# Error Handling

No new exception types. `_map_error(exc) -> LLMError`, checked in this order:

1. `litellm_sdk.Timeout`, `httpx.TimeoutException`, or builtin `TimeoutError` →
   `LLMTimeoutError`. This keeps the `api_server` 504 path reachable.
2. Any other `litellm_sdk` exception (`APIError`, `AuthenticationError`,
   `RateLimitError`, `BadRequestError`, `APIConnectionError`, `NotFoundError`, …)
   → `ProviderError(str(exc))`.
3. Anything else → `ProviderError(f"Unexpected error from LiteLLM: {exc}")`.

The mapping happens in `chat`, `achat`, and `astream_chat`, wrapping only the SDK
call and iteration. It does not wrap translation code, so `ToolCallParsingError`
and `StructuredOutputError` propagate unchanged. Keep `ToolCallParsingError`
and `StructuredOutputError` raised from the `_build_chat_response` path outside
the `try`, as today.

Exception messages from LiteLLM may echo request details. They are logged at
ERROR as today (`"Provider error: %s"`). Never log the API key.

---

# Logging

Logger name stays `jarvis.llm`. Keep the existing log lines and levels, with
`Ollama` → `LiteLLM` in text:

* DEBUG: `LLM %srequest: model=%s, messages=%d, tools=%s, schema=%s`
* DEBUG: `LLM %sresponse: finish_reason=%s, tool_calls=%d, content_len=%s`
* INFO: `Listing available LiteLLM models` (and `(async)` variant)
* TRACE: full messages, request kwargs, raw response, response content, token
  usage (`raw.usage.prompt_tokens` / `completion_tokens` when present)

The TRACE `request kwargs` line must **exclude** `api_key`. Log
`api_base`, sampling params, `response_format` name, and `timeout`. Lazy
`%s` formatting only, no f-strings in log calls.

---

# Unit Testing

`tests/unit/llm/providers/test_litellm.py` replaces `test_ollama.py`. Patch
`llm.providers.litellm.litellm_sdk.completion` / `.acompletion` /
`.get_valid_models`. Build fakes with `MagicMock` or LiteLLM's own
`ModelResponse`, whichever is simpler. No network, no live model.

Required cases:

* `_to_litellm_message` / `_to_litellm_tool` shape.
* `_build_chat_response`: plain content; tool calls with JSON-string arguments;
  tool calls with dict arguments; missing tool-call id → generated id; invalid
  JSON arguments → `ToolCallParsingError`; structured output valid / invalid JSON
  / schema mismatch → `StructuredOutputError`.
* `chat` / `achat`: correct kwargs forwarded (model override via kwargs, config
  defaults, `timeout`, `drop_params=True`, `response_format`); `api_key` /
  `api_base` forwarded when configured and `None` when not.
* Error mapping: `litellm.Timeout` and `httpx.TimeoutException` →
  `LLMTimeoutError`; a LiteLLM `APIError`-family exception → `ProviderError`;
  generic `Exception` → `ProviderError`.
* `astream_chat`: yields chunks with `provider == "litellm"`; `done` only on the
  chunk with a `finish_reason`; skips empty-`choices` chunks; mid-stream error is
  mapped.
* `list_models` / `alist_models`: return the SDK list; SDK exception →
  `ProviderError`.
* Logging: TRACE request-kwargs line never contains the API key value.

Also update:

* `tests/unit/llm/test_config.py`: drop `ollama_base_url` assertions; cover
  `llm_api_key` (is `SecretStr`, absent by default) and `llm_api_base`.
* `tests/unit/test_logging/test_debug_logging.py`: the two tests that build an
  `OllamaProvider` are retargeted to `LiteLLMProvider` with the same intent
  (TRACE logs the raw response).

The full gate (`ruff check`, `ruff format --check`, `mypy`, `pytest`) must pass
with no live model available.

---

# Documentation

* `llm/DESIGN.md`: replace the Ollama provider description, diagram boxes, and
  flow sections with LiteLLM equivalents. Keep it concise.
* `llm/README.md`: config table (remove `OLLAMA_BASE_URL`, add `LLM_API_KEY`,
  `LLM_API_BASE`, describe `DEFAULT_MODEL` as a LiteLLM model string with two or
  three examples), the model-listing caveat above, and a note on `drop_params`.
* One-line wording fixes where other docs say "Ollama" for what is now "the
  configured LLM backend": `api_server/README.md` (`GET /v1/models`),
  `api_server/DESIGN.md`, `agent_orchestration/DESIGN.md`.
* `.claude/skills/jarvis-task/SKILL.md` "Project facts" line describing `llm/`
  as having an Ollama provider → LiteLLM provider.
* Do not edit `prompts/archive/`.

---

# Non-Goals

Explicitly out of scope for this task:

* Keeping `OllamaProvider` around, or any provider-selection setting.
* Using the LiteLLM Proxy server, `litellm.Router`, fallbacks, retries,
  load balancing, caching, budgets, or cost tracking.
* Per-backend code paths, model allow-lists, or validating that `DEFAULT_MODEL`
  is a known LiteLLM model.
* Copying `.env` values into `os.environ`, or adding settings for per-provider
  keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, …).
* Streaming tool-call deltas (not supported today; still not supported).
* Multimodal content, `MessageRole.TOOL` message enrichment (`tool_call_id`,
  etc.), or any change to `llm/models.py`.
* Any change to `api_server` or `agent_orchestration` code. If one turns out to
  be required, stop and raise it in the plan.
* Token usage surfaced in `ChatResponse` (TRACE logging only, as today).
* Integration tests against a live Gemini / Ollama / OpenAI endpoint.

The implementation should be designed so these can be added later, but they
must not be implemented as part of this task.

---

# Deliverables

1. `llm/providers/litellm.py` with `LiteLLMProvider` and translation helpers.
2. `llm/providers/ollama.py` and `tests/unit/llm/providers/test_ollama.py`
   deleted.
3. `llm/config.py`: `ollama_base_url` removed, `llm_api_key` / `llm_api_base`
   added.
4. `llm/service.py` defaulting to `LiteLLMProvider`.
5. `pyproject.toml` / `uv.lock`: `ollama` removed, `litellm[google]==1.108.1`
   kept.
6. `tests/unit/llm/providers/test_litellm.py`, and updated `test_config.py` and
   `test_debug_logging.py`.
7. Updated `llm/DESIGN.md`, `llm/README.md`, and the one-line doc fixes listed
   above.
8. Full CI gate green without a live model.
