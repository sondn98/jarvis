# Tech Debt Audit — jarvis — 2026-06-21

## Summary

Jarvis is a small (~3,230 LOC source, ~3,010 LOC tests), cleanly layered
personal-agent system: a provider-agnostic `llm` module, a LangGraph-based
`agent_orchestration` module, and an OpenAI-compatible `api_server`. Overall
health is **good for its size** — consistent modern typing (Python 3.13,
Pydantic v2), clear package boundaries, dependency-injectable services, and a
genuinely strong test suite for the LLM and API layers. The debt that exists is
mostly *coherence* debt: a few features are half-wired (timeout handling, the
"agent loop", tool error capture), some scaffolding is dead (one whole store,
one stray package, a debug script), and the agent orchestration path is wired
to non-functional stub backends, so the headline feature does little in
practice. None of it is rotting fast, but several items are silently
swallowing errors or quietly dropping behaviour, which is worth fixing before
more is built on top.

**Findings by severity:** High: 2 · Medium: 8 · Low: 8 (18 total)

**Top 5, in priority order:**
1. **[H1]** Request timeouts are never reported as timeouts — the custom
   `TimeoutError` shadows the builtin and its `except` clauses are unreachable,
   so the 504 handler is dead and real timeouts surface as generic 502s.
2. **[H2]** Any tool failure aborts the whole agent run with a 500 — tools
   `raise` instead of returning a failed `ToolResult`, and `ToolResult.success`
   / `error` are never populated, contradicting the final-answer design.
3. **[M5/M6]** The advertised iterative "agent loop" is single-step only, and
   every tool backend is an inline stub, so agent orchestration is effectively
   non-functional even when enabled.
4. **[M2]** The agent code path silently drops request parameters
   (`temperature`, `top_p`, `max_tokens`, `model`, `tools`).
5. **[M3/M4]** Redundant/dead persistence (`CheckpointStore` is written but
   never read; `SessionStore` is unused) and an `errors` state field that is
   written but never surfaced.

---

## Findings

### [HIGH] Request timeouts are never reported as timeouts (shadowed `TimeoutError`)
- **Location:** `llm/exceptions.py:13`; `llm/providers/ollama.py:165-167`,
  `235-238`, `325-327`; `api_server/errors.py:16,72-77`
- **Category:** tech-debt / anti-pattern (bug)
- **Description:** `llm/exceptions.py` defines a custom `TimeoutError` that
  shadows the builtin. In the provider, the `except TimeoutError as exc: ...
  raise TimeoutError(...)` blocks catch *that custom class* (it is the imported
  name in scope), which the Ollama SDK / httpx never raise. The real timeout
  exception (`httpx.TimeoutException`, a subclass of the builtin, not of
  `LLMError`) therefore falls through to the generic `except Exception` and is
  re-wrapped as `ProviderError`. The dedicated `TimeoutError` handler in
  `api_server/errors.py:72` (HTTP 504) is consequently never reached.
- **Why it matters:** Clients can never distinguish a timeout from a generic
  provider error; the 504 path and the `raise TimeoutError(...)` lines are dead
  code that *looks* live, which will mislead the next person debugging slow
  requests.
- **Suggested fix:** Don't shadow the builtin (rename to `LLMTimeoutError`), and
  catch the actual exception type the SDK raises (`httpx.TimeoutException` or
  builtin `TimeoutError`) and translate it. Add a test that injects a timeout.
- **Effort estimate:** S

### [HIGH] Any tool failure aborts the entire agent run; `ToolResult.success`/`error` are dead
- **Location:** `agent_orchestration/graph.py:384-389`;
  `agent_orchestration/tools/{web_search,web_fetch,gmail,calendar}.py` (every
  `arun`, e.g. `web_search.py:37-38`); `agent_orchestration/models.py:18-23`
- **Category:** anti-pattern (bug) / tech-debt
- **Description:** Every tool's `arun` wraps failures in `raise
  ToolExecutionError(...)` and only ever returns `ToolResult(success=True)`.
  `_execute_tool` re-raises, so the exception propagates out of `graph.ainvoke`
  uncaught and becomes a 500. The `ToolResult.success` and `ToolResult.error`
  fields are therefore never set to a failure value — they are dead. This
  directly contradicts `_FINAL_ANSWER_SYSTEM` (`graph.py:62-66`), which
  instructs the model to "clearly state" when "a tool failed or returned no
  results" — that node can never see a failed tool because the run already
  crashed.
- **Why it matters:** A single transient tool error (network blip, bad
  argument) takes down the whole conversation turn with an opaque 500 instead
  of degrading gracefully. The intended graceful-failure design exists in the
  models and prompt but is unreachable.
- **Suggested fix:** Have tools return `ToolResult(success=False, error=...)`
  on failure (or have `_execute_tool` catch and convert), and let
  `_generate_final_answer` surface failed results.
- **Effort estimate:** M

### [MEDIUM] `chat()` and `achat()` in the Ollama provider are near-duplicates
- **Location:** `llm/providers/ollama.py:120-189` and `191-260`
- **Category:** tech-debt (duplication)
- **Description:** The sync and async chat methods are ~70 lines each and almost
  identical: same option/format/message building, same debug + TRACE logging
  blocks, same three-branch exception handling, same response logging. Only the
  client call (`self._client.chat` vs `await self._async_client.chat`) differs.
- **Why it matters:** Any change to logging, error mapping, or option building
  must be made twice and will drift (the timeout bug above already lives in both
  copies). Roughly 60 lines of avoidable maintenance surface.
- **Suggested fix:** Extract the shared pre/post logic into helpers
  (`_prepare_request`, `_log_request`, `_log_response`, `_map_error`) and keep
  only the I/O call distinct.
- **Effort estimate:** M

### [MEDIUM] Agent code path silently drops request parameters
- **Location:** `api_server/routes/chat.py:80-88`;
  `agent_orchestration/service.py:37-44`
- **Category:** structure (inconsistency)
- **Description:** When agent orchestration is enabled the route calls
  `agent_service.achat(messages)` and ignores `temperature`, `top_p`,
  `max_tokens`, `tools`, and even `model` (the request model is used only to
  *label* the response in `agent_response_to_openai`). The planner and
  final-answer LLM calls always use `LLMConfig.default_model` and defaults. The
  non-agent path (`build_llm_kwargs`) honours all of these.
- **Why it matters:** Identical requests behave differently depending on a
  server-side flag the client can't see; clients setting `temperature`/`model`
  are silently ignored — confusing and hard to diagnose.
- **Suggested fix:** Thread generation kwargs through `AgentService.achat`
  (which already accepts `**kwargs`) into the planner/final-answer calls, or
  explicitly document and reject unsupported params.
- **Effort estimate:** M

### [MEDIUM] Redundant and dead persistence layer
- **Location:** `agent_orchestration/persistence/checkpoint_store.py` (whole
  file); `agent_orchestration/persistence/session_store.py` (whole file);
  `agent_orchestration/graph.py:468-469`, `276-296`
- **Category:** tech-debt (dead code) / structure
- **Description:** Approval resume saves state to *both* `ApprovalStore`
  (`record.graph_state`) and `CheckpointStore` (`_save_checkpoint`,
  `graph.py:469`), but `_load_checkpoint` restores from
  `approval_store.get(...).graph_state` only — `CheckpointStore.load` / `.delete`
  are never called anywhere. `SessionStore` is exported from
  `persistence/__init__.py` but never instantiated or imported anywhere.
- **Why it matters:** Two parallel copies of the same checkpoint that can drift;
  a reader can't tell which store is authoritative. ~70 LOC of dead scaffolding
  implies capabilities that don't exist.
- **Suggested fix:** Either make `CheckpointStore` the single source of truth
  (read from it on resume and drop the duplicate field) or delete it; delete
  `SessionStore` until something needs it.
- **Effort estimate:** S

### [MEDIUM] `errors` state field is written but never surfaced; validation failure is swallowed
- **Location:** `agent_orchestration/graph.py:339-359` (esp. `343-348`),
  `state.py:28`, `service.py:62-72`
- **Category:** anti-pattern (silent failure)
- **Description:** `AgentState.errors` is only ever appended to in one place
  (`_validate_tool_call` when `selected_tool_call` is `None`,
  `graph.py:345`) and is never read or returned by `AgentService.achat`. In that
  same `None` case the node appends an error and then *returns and continues* to
  `risk_check` → `execute_tool` (which no-ops on `None`) → final answer, instead
  of aborting. Meanwhile sibling failures in the same function (`ToolNotFound`,
  `ToolValidationError`) `raise`. Error handling is thus inconsistent within one
  function: some failures crash, one is silently dropped.
- **Why it matters:** A malformed plan can quietly produce a final answer with
  no tool executed and no signal to the caller — hard to detect and debug.
- **Suggested fix:** Decide on one strategy — either surface `errors` in
  `AgentResponse` or remove the field and raise consistently.
- **Effort estimate:** S

### [MEDIUM] Advertised iterative "agent loop" is single-step only
- **Location:** `agent_orchestration/graph.py:1-21` (docstring), `401-408`,
  `548-552`
- **Category:** structure / documentation
- **Description:** The module docstring shows `execute_tool → decide_next_step
  (loop)`, implying multi-tool/iterative execution. But `_execute_tool` sets
  `plan=None` and `selected_tool_call=None` (`graph.py:405-406`), so
  `_route_decide_next_step` always returns `no_tool` on the next pass. The
  planner also only ever returns a single `tool_call` and there is no
  re-planning node. The "loop" never iterates.
- **Why it matters:** The architecture diagram overstates capability; anyone
  extending toward multi-step agents will assume the plumbing exists when it
  doesn't.
- **Suggested fix:** Either implement re-planning after tool execution, or
  correct the docstring/diagram to reflect single-step execution.
- **Effort estimate:** M (to implement) / S (to correct docs)

### [MEDIUM] Tool backends are inline stubs; agent feature is non-functional when enabled
- **Location:** `api_server/app.py:35-117`
- **Category:** structure
- **Description:** `_build_agent_service` defines five stub backend classes
  *inside the function body* (`_StubWebSearch`, `_StubGmail`, etc.), each with
  per-method local `import`s, all returning empty lists or `"not_configured"`
  placeholders. There are no real backend implementations anywhere in the repo
  (`tools/backends.py` defines only Protocols). So with
  `ENABLE_AGENT_ORCHESTRATION=true`, web search returns nothing, Gmail/calendar
  are no-ops.
- **Why it matters:** The headline feature does nothing useful; the stubs are
  easy to mistake for real wiring. Nested class/function definitions plus
  repeated inline imports are hard to test and reuse.
- **Suggested fix:** Move stubs to a dedicated `tools/backends_stub.py` (or
  real implementations behind a config switch), and select the backend set via
  config rather than hardcoding stubs in app construction.
- **Effort estimate:** M

### [MEDIUM] No static type checking in CI despite pervasive type hints
- **Location:** `.github/workflows/ci.yml:18-123`; `# type: ignore` usages in
  `logging_utils/__init__.py:22,25`, `llm/providers/base.py:48`,
  `agent_orchestration/graph.py:74-75`
- **Category:** test-gap / structure
- **Description:** The codebase is fully type-annotated and already sprinkles
  `# type: ignore`, but CI runs only ruff (lint+format), pip-audit, and pytest —
  no mypy/pyright gate. Type regressions and the kind of name-shadowing behind
  H1 would be caught by a type checker.
- **Why it matters:** The investment in typing isn't being enforced; the
  `type: ignore`s can silently widen over time.
- **Suggested fix:** Add a mypy or pyright job to CI.
- **Effort estimate:** S (add job) / M (fix initial findings)

### [MEDIUM] No direct test coverage for tool implementations or the agent OpenAI adapter
- **Location:** `agent_orchestration/tools/{web_search,web_fetch,gmail,calendar}.py`
  (~300 LOC); `agent_orchestration/adapters/openai_adapter.py`
- **Category:** test-gap
- **Description:** No test references `WebSearchTool`, `WebFetchTool`, any Gmail
  or Calendar tool, or `agent_response_to_openai`. The graph tests use mock
  tools, so the real `arun` paths (argument parsing, JSON serialization, the
  `ToolExecutionError` wrapping in H2) and the agent→OpenAI conversion are
  untested.
- **Why it matters:** The error-handling and serialization code most likely to
  break (and central to H2) has zero direct coverage.
- **Suggested fix:** Add per-tool tests with fake backends covering success and
  failure, plus a test for `agent_response_to_openai`.
- **Effort estimate:** S

### [LOW] Stray empty top-level `tools/` package
- **Location:** `tools/__init__.py` (empty); duplicates the name of
  `agent_orchestration/tools/`
- **Category:** tech-debt (dead code)
- **Description:** An empty top-level `tools` package exists, is never imported,
  and is not copied into the Docker image. It collides conceptually with the
  real `agent_orchestration/tools` package.
- **Why it matters:** Import-path confusion and noise.
- **Suggested fix:** Delete it.
- **Effort estimate:** S

### [LOW] `test.py` debug script committed at repo root
- **Location:** `test.py`
- **Category:** tech-debt
- **Description:** A manual debug harness that builds the planner prompt with
  `MagicMock` backends and calls a live Ollama (`localhost:11434`,
  `qwen3:1.7b`) at import time via `asyncio.run(...)`. It is not a pytest test
  (the name doesn't match `test_*.py`, so it isn't collected) and imports
  internal modules directly. (Also currently modified in the working tree.)
- **Why it matters:** Clutter that looks like a test, depends on a running
  Ollama, and will rot as internals change.
- **Suggested fix:** Move under `scripts/` or delete; if it encodes a useful
  regression check, convert it into a real (mocked) test.
- **Effort estimate:** S

### [LOW] Vestigial no-op graph nodes
- **Location:** `agent_orchestration/graph.py:328-332` (`_validate_plan`),
  `334-337` (`_decide_next_step`), `361-364` (`_risk_check`)
- **Category:** anti-pattern (premature structure)
- **Description:** Three nodes do nothing but log start/end and return state
  unchanged; the actual decisions live in the router functions
  (`_route_decide_next_step`, `_route_risk_check`). They exist only as graph
  labels.
- **Why it matters:** Extra indirection to read through; implies logic that
  isn't there. (Minor — they do aid the trace/diagram.)
- **Suggested fix:** Collapse into the routers, or add a comment that they exist
  purely as instrumentation anchors.
- **Effort estimate:** S

### [LOW] Tool arguments validated twice
- **Location:** `agent_orchestration/graph.py:351-356` and each tool's `arun`
  (e.g. `web_search.py:28`, `calendar.py:52`)
- **Category:** tech-debt (duplication)
- **Description:** `_validate_tool_call` instantiates `tool.args_schema(**args)`,
  then `arun` re-instantiates the same model from the same dict.
- **Why it matters:** Minor wasted work and a second place to keep in sync.
- **Suggested fix:** Validate once (e.g. pass the parsed model into `arun`, or
  drop the graph-level pre-validation and rely on `arun`).
- **Effort estimate:** S

### [LOW] IDE config committed to the repo
- **Location:** `.idea/` (`jarvis.iml`, `misc.xml`, `modules.xml`, etc.)
- **Category:** tech-debt
- **Description:** JetBrains project files are tracked in git.
- **Why it matters:** Machine/user-specific noise in diffs.
- **Suggested fix:** Remove from tracking and add to `.gitignore`.
- **Effort estimate:** S

### [LOW] `default_model` configured in two places
- **Location:** `llm/config.py:15` (required) and `api_server/config.py:14`
  (optional, separate field)
- **Category:** structure (inconsistency)
- **Description:** `LLMConfig.default_model` (required) and
  `APIServerConfig.default_model` (optional) are two independent settings. The
  API one is used as a fallback in the non-agent path; the agent path uses the
  LLM one. Two sources of truth for "which model".
- **Why it matters:** Easy to set one and expect the other to apply.
- **Suggested fix:** Pick one owner for the default model, or document the
  precedence clearly.
- **Effort estimate:** S

### [LOW] TRACE logging may leak nested sensitive data
- **Location:** `logging_utils/__init__.py:72-97`; TRACE calls in
  `llm/providers/ollama.py:140-152,179-188` and
  `agent_orchestration/graph.py` node tracing
- **Category:** tech-debt (security smell)
- **Description:** `redact()` handles only top-level `str` and `dict`; nested
  structures (e.g. a list of message dicts logged via `%s`) are stringified by
  `LogRecord.getMessage()` so only regex-based redaction applies — key-based
  redaction of nested dicts does not. TRACE logs full messages, raw responses,
  and tool payloads.
- **Why it matters:** Sensitive content in nested fields could pass through at
  TRACE level. Low because TRACE is opt-in and off by default.
- **Suggested fix:** Make `redact()` recurse into lists/tuples, or avoid logging
  full payloads even at TRACE.
- **Effort estimate:** S

### [LOW] No pytest/ruff config block; no coverage tooling
- **Location:** `pyproject.toml` (no `[tool.pytest.ini_options]`, no
  `[tool.ruff]`, no coverage dep)
- **Category:** test-gap
- **Description:** pytest-asyncio runs in default (strict) mode, working only
  because all 32 async tests carry explicit `@pytest.mark.asyncio` markers — one
  forgotten marker silently won't run. No `pytest-cov`, so coverage can't be
  measured in CI; ruff uses defaults only.
- **Why it matters:** Fragile test discovery and no objective coverage signal.
- **Suggested fix:** Add `[tool.pytest.ini_options]` with
  `asyncio_mode = "auto"`, and wire `pytest-cov` with a CI threshold.
- **Effort estimate:** S

---

## Test coverage summary

The suite is strong where it exists (~3,010 test LOC vs ~3,230 source LOC) and
weak in a few specific, important spots.

| Module / area | Coverage | Notes |
|---|---|---|
| `llm/` (config, models, service, ollama provider) | Strong | `test_ollama.py` (254 LOC) + service/config/model tests. **Gap:** no timeout-path test (would expose H1). |
| `api_server/` routes + adapters + errors | Strong | `test_chat.py` (208), adapter + error-handler tests present. |
| `agent_orchestration/graph.py` | Good | `test_graph.py` (642 LOC) covers approval/reject/routing — but with **mock tools**, so real `arun`/error paths are untouched. |
| `agent_orchestration/tools/*` (web_search, web_fetch, gmail, calendar) | **None (direct)** | ~300 LOC of real tool code, no dedicated tests. Central to H2. |
| `agent_orchestration/adapters/openai_adapter.py` | **None** | Untested. |
| `agent_orchestration/persistence/session_store.py` | **None** | Dead code (M3). |
| `logging_utils` | Strong (but…) | `test_debug_logging.py` is 525 LOC — see note below. |

**Pattern-level notes:**
- Heavy reliance on mocking in the graph tests means the suite verifies *control
  flow* well but not the tool I/O / serialization boundary — exactly where the
  H2 bug lives.
- No error-injection tests for provider timeouts (H1) or tool failures (H2);
  the suite is largely happy-path + approval-flow.
- `test_debug_logging.py` at 525 LOC is disproportionately large for a logging
  utility and is worth a skim for over-mocking / testing log formatting rather
  than behaviour (not audited line-by-line).
- No coverage tool is configured, so these are qualitative assessments, not
  measured percentages.

---

## Open questions

1. **Stub backends** (`app.py:35-117`): are real Web/Gmail/Calendar backends
   planned in this repo, or is jarvis intended to be deployed with externally
   supplied backends? This determines whether M6 is "finish the feature" or
   "this is intentional placeholder wiring".
2. **`CheckpointStore` vs `ApprovalStore.graph_state`** (M3): is the dual write
   intentional groundwork for separating approval metadata from graph
   checkpoints, or accidental redundancy? Affects whether to delete or wire up.
3. **`prompts/`, `assets/`, `.idea/`** were treated as non-source (docs/IDE)
   and not audited for code-quality issues; confirm that's the intended scope.
4. **DESIGN.md / README.md files** were not line-audited for drift against code
   (e.g. the "agent loop" claim in M5). Want me to cross-check docs against the
   implementation as a follow-up?
