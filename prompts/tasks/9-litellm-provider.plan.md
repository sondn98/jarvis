# LiteLLM Provider – Implementation Plan

Source spec: `prompts/tasks/9-litellm-provider.md`.

Context verified while planning (litellm 1.108.1 installed in `.venv`):

- `litellm.Timeout` subclasses `APITimeoutError → APIConnectionError → APIError`,
  so `_map_error` must test `Timeout` **before** the generic LiteLLM branch.
- `litellm.get_valid_models()` is sync-only; with no provider keys exported it
  returns `[]`.
- `import litellm` takes ~2.75s here and, by default, fetches the remote model
  cost map at import time (falls back to the bundled copy on failure). See
  Question 3.
- `api_server/adapters/llm_to_openai.py` already maps OpenAI-style
  `finish_reason`s (`stop`, `length`, `tool_calls`, `content_filter`), and its
  streaming path only reads `chunk.done` / `chunk.finish_reason`, so no
  `api_server` change is needed.
- Ollama is referenced in code only inside `llm/`, plus two tests in
  `tests/unit/test_logging/test_debug_logging.py` (lines 157, 409).

---

## Architecture Summary

1. `llm/providers/litellm.py` — new `LiteLLMProvider(BaseProvider)`. It holds the
   module-level translation helpers `_to_litellm_message`, `_to_litellm_tool`,
   `_parse_tool_calls`, `_build_chat_response` and `_map_error`, plus shared
   `_prepare_request` / `_log_request` / `_log_response`. It calls
   `litellm_sdk.completion` / `acompletion` / `get_valid_models`. No client
   objects are needed, because LiteLLM is called through module functions.
2. `llm/providers/ollama.py` — deleted.
3. `llm/config.py` — `ollama_base_url` removed. `llm_api_key: SecretStr | None`
   and `llm_api_base: str | None` added (subject to Q1).
4. `llm/service.py` — default provider `OllamaProvider(config)` →
   `LiteLLMProvider(config)`. No signature changes.
5. `llm/__init__.py`, `llm/models.py`, `llm/exceptions.py`,
   `llm/providers/base.py` — unchanged.
6. `pyproject.toml` / `uv.lock` — `ollama` removed; `litellm[google]==1.108.1`
   (already pinned by owner) kept; mypy comment no longer names `ollama`.
7. `tests/unit/llm/providers/test_litellm.py` — replaces `test_ollama.py`.
   Patches `llm.providers.litellm.litellm_sdk.*`, so no network or live model.
8. `tests/unit/llm/test_config.py` and
   `tests/unit/test_logging/test_debug_logging.py` — updated for the new config
   fields and retargeted to `LiteLLMProvider`.
9. `llm/DESIGN.md`, `llm/README.md` — rewritten provider sections, config table,
   model-listing caveat.
10. One-line doc fixes: `api_server/README.md`, `api_server/DESIGN.md`,
    `agent_orchestration/DESIGN.md`, `.claude/skills/jarvis-task/SKILL.md`.

---

## Directory Structure

```text
llm/
├── __init__.py              (unchanged)
├── config.py                (modified)
├── exceptions.py            (unchanged)
├── models.py                (unchanged)
├── service.py               (modified)
├── DESIGN.md                (modified)
├── README.md                (modified)
└── providers/
    ├── __init__.py          (unchanged)
    ├── base.py              (unchanged)
    └── litellm.py           (NEW)          # ollama.py deleted

tests/
└── unit/
    ├── llm/
    │   ├── test_config.py           (modified)
    │   ├── test_service.py          (unchanged — injects a mock provider)
    │   └── providers/
    │       └── test_litellm.py      (NEW)  # test_ollama.py deleted
    └── test_logging/
        └── test_debug_logging.py    (modified — 2 tests)
```

---

## Planning Questions

> Every question must be answered by the owner before execution begins.
> Leave each `[Answer]` empty — the owner fills it in.

### [Question 1]

How does Jarvis hand credentials and a custom endpoint to LiteLLM?

`pydantic-settings` reads `.env` into `LLMConfig` but does **not** export it to
`os.environ`. LiteLLM only sees its native env vars (`GEMINI_API_KEY`, …) if
they are actually exported in the process environment.

Options:

- **Option A — explicit `LLM_API_KEY` (`SecretStr`) + `LLM_API_BASE` fields** in
  `LLMConfig`. Each is passed as `api_key=` / `api_base=` on every call when set,
  and `None` otherwise, so LiteLLM's own env resolution still works. Works from
  `.env`. Tradeoff: one key for the one configured model. If you later mix
  backends (e.g. a Gemini default plus an OpenAI override via `model=` kwarg), the
  single key gets sent to both.
- **Option B — no new fields; rely on LiteLLM native env vars only.** Smallest
  diff. Tradeoff: keys in `.env` silently don't work; operators must `export`
  them (or use `uv run --env-file .env`). Pointing at a non-default host such as
  remote Ollama would need LiteLLM's own `OLLAMA_API_BASE` etc.
- **Option C — Option A, but only `LLM_API_BASE`.** Credentials always come from
  exported native env vars. Tradeoff: still has B's `.env` surprise for keys.

Recommendation: **A**. It is the only option where the existing `.env`
convention actually works, and it is what the spec prescribes. The mixed-backend
issue is hypothetical today, because there is one `DEFAULT_MODEL`.

Why this is critical: configuration format and env-var names.

## [Answer 1]
Option A

### [Question 2]

Should unsupported sampling params be silently dropped (`drop_params=True`)?

Jarvis always sends `temperature`, `top_p` and `max_tokens`. Some backends or
models reject one of them, and LiteLLM then raises `UnsupportedParamsError`,
which becomes `ProviderError` → HTTP 502.

Options:

- **Option A — always `drop_params=True`.** Any `DEFAULT_MODEL` just works.
  Tradeoff: a configured `DEFAULT_TOP_P` can be ignored with no error. DEBUG
  logs still show what was sent.
- **Option B — `drop_params=False` (LiteLLM default).** Fails loudly; the
  operator adjusts config. Tradeoff: some models are unusable without code or
  config changes, which cuts against "any LiteLLM model".
- **Option C — config flag `LLM_DROP_PARAMS` (default `true`).** Tradeoff: a new
  setting nobody has asked for yet.

Recommendation: **A**. It matches the "any LiteLLM model" answer from the spec
phase, and C is speculative configurability.

Why this is critical: observable behaviour of the public API for every request.

## [Answer 2]
Option A

### [Question 3]

How should Jarvis handle LiteLLM's import-time remote fetch of its model cost
map?

By default `import litellm` makes an outbound HTTP request to GitHub for
`model_prices_and_context_window.json`, falling back to the bundled copy on
failure. Setting the env var `LITELLM_LOCAL_MODEL_COST_MAP=True` skips the
request. This affects app start-up, every pytest run, and CI. It is an outbound
call from what was a local-only app.

Options:

- **Option A — leave the default; document it** in `llm/README.md`, including the
  env var to disable it. Zero code. Tradeoff: offline start-up and test runs pay
  a network timeout before the fallback kicks in, and the request is made
  silently.
- **Option B — force local in code**:
  `os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")` at the top of
  `llm/providers/litellm.py`, before `import litellm`. Deterministic everywhere;
  an operator can still override it. Tradeoff: an import-order side effect
  (needs a `# noqa: E402`) that mutates the process env, and any code importing
  `litellm` before `llm` bypasses it.
- **Option C — set it outside the code**: in `.github/workflows/ci.yml` env and
  `tests/conftest.py` (`os.environ.setdefault` before imports), plus a README
  note for runtime. Tests and CI become deterministic, while runtime behaviour
  stays the LiteLLM default. Tradeoff: touches CI and the conftest, which the spec
  does not list.

Recommendation: **A**, unless offline or CI flakiness actually shows up. Then
prefer **C** over B, because it keeps import-time side effects out of library
code. Not deciding it myself because it adds an outbound network call to the app.

Why this is critical: runtime network behaviour, CI configuration.

## [Answer 3]
Option A

### [Question 4] (raised during execution)

Discovered in Step 3: `import litellm` runs `dotenv.load_dotenv()`
(`litellm/__init__.py:30`, gated on `LITELLM_MODE == "DEV"`, which is the default).
This copies every value in the repo `.env` into `os.environ`, process-wide.
Effects: local test runs pick up `.env` values (`REQUEST_TIMEOUT=180` broke 2 tests
locally; 252/252 pass on a clean checkout); native provider keys in `.env` *do*
reach LiteLLM, which corrects the Q1 rationale, although Q1=A still stands; and
`${VAR}` in `mcp.json` now also resolves from `.env`. MCP stdio children still
get only `mcp`'s safe env allowlist.

Options: A — accept and document; B — set `LITELLM_MODE=PRODUCTION` in
`tests/conftest.py` only; C — set it in `llm/providers/litellm.py` before import.

## [Answer 4]
Option A — accept LiteLLM's default, document it in `llm/README.md` (Step 8).

---

## Implementation Steps

> Not executed until every planning question above has a non-empty answer and
> the owner approves the plan.

Order keeps the repo green between items: build and switch to the new provider
first, delete Ollama code next, remove the dependency last.

- [x] **Step 1 – Config** (Q1 = A): `llm/config.py` — remove
      `ollama_base_url`; add `llm_api_key: SecretStr | None = None` and
      `llm_api_base: str | None = None` (or the subset Q1 selects). Update
      `tests/unit/llm/test_config.py`: drop `ollama_base_url` assertions; assert
      both new fields default to `None`; assert `llm_api_key` is a `SecretStr`
      whose `repr` does not contain the value. `OllamaProvider` still reads
      `config.ollama_base_url` until Step 4, so in this step replace that read with
      the Ollama SDK default by passing `host=None`. It is a temporary bridge,
      deleted in Step 5.
- [x] **Step 2 – LiteLLM provider** (Q1/Q2/Q3 = A) — *note: LiteLLM exceptions do not share `litellm.APIError` (e.g. `UnsupportedParamsError` → openai `BadRequestError`), and `litellm.exceptions.OpenAIError` is a subclass, not the base; the provider branch matches `tuple(litellm.exceptions.LITELLM_EXCEPTION_TYPES)` instead. Module name `litellm.py` caused no shadowing issues.* Create
      `llm/providers/litellm.py` per the spec. It covers:
      request translation (`model`, `messages`, `tools`, `response_format`,
      `temperature`, `top_p`, `max_tokens`, `timeout`, `api_key`, `api_base`,
      `drop_params`); response translation (`choices[0]`, tool-call id
      fallback, JSON-string or dict arguments → `ToolCallParsingError` on
      failure); structured-output validation → `StructuredOutputError`;
      `_map_error` in order `litellm_sdk.Timeout` / `httpx.TimeoutException` /
      `TimeoutError` → `LLMTimeoutError`, any other `litellm_sdk.exceptions`
      type → `ProviderError(str(exc))`, else
      `ProviderError("Unexpected error from LiteLLM: …")`; streaming
      (`provider="litellm"`, `done` on the `finish_reason` chunk, skip empty
      `choices`); `list_models` via `get_valid_models()`, `alist_models` via
      `asyncio.to_thread`; logging that mirrors the Ollama lines, with `api_key`
      excluded from the TRACE request-kwargs line.
- [x] **Step 3 – Provider tests** — *36 tests; 252/252 pass on a clean checkout. Locally they hit `.env` leakage, see Question 4.* Create
      `tests/unit/llm/providers/test_litellm.py` with every case listed in the
      spec's *Unit Testing* section: helpers, `_build_chat_response` variants,
      `chat`/`achat` kwargs forwarding (incl. `api_key`/`api_base` set and unset,
      `drop_params`), error mapping (`litellm.Timeout`,
      `httpx.TimeoutException`, a LiteLLM `APIError` subclass, generic
      `Exception`), streaming (provider tag, `done` semantics, empty-`choices`
      skip, mid-stream error), model listing (success, `ProviderError`), and the
      "API key never in TRACE" test.
- [x] **Step 4 – Switch default** (docstring had no Ollama mention): `llm/service.py` — import and default to
      `LiteLLMProvider(config)`; update the docstring if it names Ollama.
- [x] **Step 5 – Remove Ollama provider** (Step 1's `host=None` bridge removed with the file): delete `llm/providers/ollama.py` and
      `tests/unit/llm/providers/test_ollama.py`. In
      `tests/unit/test_logging/test_debug_logging.py`, retarget
      `test_ollama_trace_logs_raw_response` (rename to
      `test_litellm_trace_logs_raw_response`) and `test_streaming_debug_logs` to
      `LiteLLMProvider`, by patching `llm.providers.litellm.litellm_sdk.acompletion`
      with OpenAI-shaped fakes. Keep the same assertions ("raw response" TRACE;
      `Stream started` / `Stream completed` / `chunks=3`).
- [x] **Step 6 – Dependencies** (uv.lock: only the `ollama` entry removed): `uv remove ollama` (updates `pyproject.toml` and
      `uv.lock`); keep `litellm[google]==1.108.1`; change the mypy comment in
      `pyproject.toml` from "(langgraph, ollama, etc.)" to
      "(langgraph, litellm, etc.)". Confirm `import ollama` appears nowhere
      outside `.venv` / `prompts/archive`.
- [x] **Step 7 – Question 3 follow-through** — *skipped: Q3 = A, README note folded into Step 8*: apply
      whichever option was chosen. A = README note only (folded into Step 8).
      B = `os.environ.setdefault` in `llm/providers/litellm.py`. C = env in
      `.github/workflows/ci.yml` + `tests/conftest.py`. Skip if A.
- [x] **Step 8 – `llm` docs** (also documented Q4's `.env` → `os.environ` behaviour; dropped 'Additional providers' from DESIGN roadmap/status since LiteLLM covers it; README override example → `ollama_chat/mistral`): `llm/DESIGN.md` (provider bullets, diagram box,
      request/tool/structured/stream flow sections, "only Ollama" limitation →
      "only LiteLLM") and `llm/README.md` (config table: remove
      `OLLAMA_BASE_URL`, add `LLM_API_KEY` / `LLM_API_BASE`, `DEFAULT_MODEL` as a
      LiteLLM model string with examples `gemini/gemini-2.5-flash`,
      `ollama_chat/llama3.2`, `openai/gpt-4o-mini`; `drop_params` note;
      `list_models` caveat; cost-map note per Q3).
- [x] **Step 9 – Cross-module doc one-liners** (also `.claude/skills/jarvis-task/README.md:103`, same sentence as SKILL.md:172): `api_server/README.md:12`,
      `api_server/DESIGN.md` (lines ~51, 79-80, 208), `agent_orchestration/DESIGN.md:21`,
      `.claude/skills/jarvis-task/SKILL.md` (the "Project facts" `llm/` line and
      the "live Ollama / `DEFAULT_MODEL`" gate note → "live model /
      `DEFAULT_MODEL`").
- [x] **Step 10 – Leftover sweep** (remaining: docs backend examples; `"ollama down"` error strings in `tests/unit/api_server/test_errors.py:41` and `routes/test_chat.py:161`; `test_main.py:13` docstring; an old permission entry in `.claude/settings.local.json:5` — all left as-is): `grep -rniE 'ollama'` excluding `.venv`,
      `uv.lock`, and `prompts/archive`. Expected hits: only intentional ones
      (README `ollama_chat/` example, test docstrings/fixture strings that don't
      claim an Ollama connection). List any remaining hits in the final report
      rather than fixing them silently.
- [x] **Step 11 – Verify** — *clean checkout: ruff ✓, format ✓, pytest 234/234 ✓; mypy 37 errors, all pre-existing in `agent_orchestration`/`api_server` (39 on master; the 2 removed were in `ollama.py`). Working copy with owner `.env`: 45 failures = master's 44 `.env`-caused + `test_forwards_defaults` (same `REQUEST_TIMEOUT` leak, Q4 = A).*: full gate —
      `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`

---

## Verification

- Step 1: `uv run pytest tests/unit/llm/test_config.py` and
  `tests/unit/llm/providers/test_ollama.py` (the bridge must keep it green).
- Steps 2–3: `uv run pytest tests/unit/llm/providers/test_litellm.py`; `uv run mypy`.
- Step 4: `uv run pytest tests/unit/llm/ tests/unit/api_server/ tests/unit/main/`.
  `api_server/app.py:70` builds `LLMService(LLMConfig())` by default, so check
  that `test_main` / lifespan tests still mock it and never construct a real
  provider.
- Step 5: `uv run pytest tests/unit/test_logging/ tests/unit/llm/`.
- Step 6: `uv sync` succeeds; `uv run pytest`; `grep` confirms no `import ollama`.
- Step 7: per option. A: manual review of the README text. B: a test asserting
  the env default is set after import. C: CI file and conftest manual review.
- Steps 8–10: manual review of the diffs.
- Before reporting done: the full gate (Step 11). No test may need a live model
  or network. Under Q3=A, the import-time cost-map fetch is attempted, but tests
  must not depend on its result.

---

## Out of scope / deferred

- Everything in the spec's *Non-Goals*: Router/proxy/fallbacks, provider
  selection, per-backend code, streaming tool-call deltas, `llm/models.py`
  changes, `api_server` / `agent_orchestration` code changes.
- `tests/unit/main/test_main.py:13` docstring mentions "no Ollama connection".
  It's a test docstring that's still loosely true in spirit, so leave it unless
  the Step 10 sweep is told otherwise.
- `tests/conftest.py` fixture `default_model="llama3.2"` and the `llama3.2`
  strings in `test_config.py` are arbitrary model strings, so they're left as-is.
- Slow `import litellm` (~2.75s) at app start: noted, not optimized (no lazy
  import).

---

## Notes / flagged assumptions (reversible)

- Module named `llm/providers/litellm.py` with `import litellm as litellm_sdk`.
  Python 3 absolute imports resolve `litellm` to the top-level package, not the
  sibling module. If mypy or ruff complain about the shadowing, rename the module
  to `litellm_provider.py` and note it on the Step 2 checkbox.
- Test fakes: use `MagicMock` objects shaped like `ModelResponse` /
  `ModelResponseStream`, consistent with the existing Ollama tests. Switch to
  real `litellm.ModelResponse` only if the mocks become awkward.
- `_map_error`'s "LiteLLM exception" branch checks
  `isinstance(exc, litellm_sdk.exceptions.APIError)` plus `openai.OpenAIError`,
  the shared base. If some LiteLLM exceptions fall outside both, they still land
  in the generic `ProviderError` branch, so the user-visible behaviour is the
  same.
- `Step 1`'s `host=None` bridge exists only so the repo stays green between
  Steps 1 and 5. It is deleted along with `ollama.py`.
