# Remediation Plan — 2026-06-21

> Source audit: `prompts/tasks/7-tech-debt.md` (18 findings: 2 High, 8 Medium,
> 8 Low). Note: the workflow prompt `7-resolve-tech-debts.md` self-references as
> the audit file, but the actual audit produced by the previous pass is
> `7-tech-debt.md` — that is what this plan is built from.

## Test verification

- **Runnable test suite?** Yes — `uv run pytest` (pytest 9 + pytest-asyncio,
  strict mode; ~3,010 LOC of tests). CI runs `uv run pytest`, ruff, pip-audit.
- **How fixes are verified:** Primarily by tests (new + existing), plus manual
  review of the diff. After each work item the relevant tests (or the full
  suite if scope is unclear) are run before moving on. No coverage tool is
  configured today (see L8).

## Question summary

8 `[Question]` blocks need answers before their items are Phase-2 ready:
Q-H1, Q-M2, Q-M3, Q-M4, Q-M5, Q-M6, Q-M7, Q-L2. All other items are mechanical
and ready to execute.

---

## Work items

### Item 1 [H1]: Request timeouts never reported as timeouts (shadowed `TimeoutError`)
- **Source finding:** [HIGH] shadowed `TimeoutError`
- **Severity / Effort:** High / S
- **Depends on / conflicts with:** Item 3 (M1) should be done right after this so
  the timeout fix is consolidated once, not duplicated. Item 9 (M8) adds the
  missing timeout test.
- **Verification:** New test injecting `httpx.TimeoutException` into the Ollama
  client and asserting a translated timeout exception → 504 via the API handler.
  Existing `tests/unit/api_server/test_errors.py` and `test_ollama.py:186`
  (already imports `TimeoutError as LLMTimeout`) updated to the new name.
- **Notes from code:** `TimeoutError` is exported from `llm/__init__.py` (public
  API). The `except TimeoutError` blocks catch the custom class, which the SDK
  never raises; real timeouts are `httpx.TimeoutException` (NOT a subclass of
  builtin `TimeoutError`). `httpx` 0.28.1 is already installed (transitive via
  `ollama`/`uvicorn`).

## [Question]
Q-H1: H1's fix is a public-API change. Two coupled sub-decisions:
(a) Rename the custom `llm.exceptions.TimeoutError` → `LLMTimeoutError` (and
    update `llm/__init__.py`, `api_server/errors.py`, and the two tests), or
    keep the name `TimeoutError` and just fix the `except`/raise targets?
(b) Add `httpx` as an explicit runtime dependency in `pyproject.toml`
    (currently only a transitive dep) so importing it in `ollama.py` is
    declared, or rely on the transitive install?
Recommended: rename to `LLMTimeoutError` (removes the builtin shadow that
caused the bug; a type checker from M7 would flag the shadow) + add `httpx`
explicitly.

## [Answer]
Follow your recommendation

- [x] (blocked on Q-H1) Decide rename vs keep-name; if rename, update
      `llm/exceptions.py`, `llm/__init__.py` (`__all__` + import),
      `api_server/errors.py`, `tests/unit/api_server/test_errors.py`,
      `tests/unit/llm/providers/test_ollama.py`.
- [x] (blocked on Q-H1) In `llm/providers/ollama.py` `chat`/`achat`/`astream_chat`,
      catch `httpx.TimeoutException` (and builtin `TimeoutError`) and re-raise as
      the LLM timeout exception; keep `except ollama_sdk.ResponseError` ahead of
      it and the generic `except Exception` last.
- [x] (blocked on Q-H1) If adding `httpx` explicitly, add it to `pyproject.toml`
      `dependencies` and refresh `uv.lock`.
- [x] Add a timeout-injection unit test (see Item 9 verification) and confirm the
      504 path in `api_server/errors.py` is now reachable.

### Item 2 [H2]: Any tool failure aborts the whole agent run; `ToolResult.success`/`error` dead
- **Source finding:** [HIGH] tool failure → 500; dead `ToolResult.success/error`
- **Severity / Effort:** High / M
- **Depends on / conflicts with:** Enables Item 9 (M8) tool failure-path tests;
  interacts with Item 13 (L4) validation semantics.
- **Verification:** New tests: a tool whose backend raises → graph completes with
  `ToolResult(success=False, error=...)` and a final answer that surfaces the
  failure (not a 500). Existing `test_graph.py` still passes.
- **Approach (mechanical, no question):** Convert failures centrally in
  `graph.py::_execute_tool` — wrap `await tool.arun(...)` so that
  `ToolExecutionError`/`Exception` become
  `ToolResult(tool_name=tc.tool_name, arguments=tc.arguments, output="",
  success=False, error=str(exc))` appended to `tool_results`, instead of
  re-raising. Then in `_generate_final_answer`, include the failure in
  `results_context` (e.g. show `error` when `not r.success`) so the existing
  `_FINAL_ANSWER_SYSTEM` prompt ("if a tool failed … clearly state that") can
  act on it. Leave the `ToolExecutionError` handler in `api_server/errors.py`
  as a backstop. This keeps tool `arun` implementations untouched.

- [x] In `_execute_tool`, replace the `raise` paths with conversion to a failed
      `ToolResult` and append it to `tool_results`.
- [x] In `_generate_final_answer`, render failed results (include `r.error`) in
      `results_context`.
- [x] Add graph-level tests for the tool-failure path (ties into Item 9).

### Item 3 [M1]: `chat()` / `achat()` near-duplicates in Ollama provider
- **Source finding:** [MEDIUM] sync/async chat duplication
- **Severity / Effort:** Medium / M
- **Depends on / conflicts with:** Do immediately after Item 1 so the timeout fix
  is captured once in the shared helpers.
- **Verification:** `tests/unit/llm/providers/test_ollama.py` (254 LOC) passes
  unchanged — behavior must be identical.
- **Approach (mechanical, no question):** Extract shared logic into private
  helpers: `_prepare_request(messages, tools, response_model, **kwargs)`,
  `_log_request(...)`, `_log_response(...)`, and `_map_error(exc)` (single place
  for the `ResponseError` / timeout / generic mapping). `chat`/`achat` keep only
  the distinct sync vs `await` client call.

- [x] Extract `_prepare_request` / `_log_request` / `_log_response` / `_map_error`.
- [x] Rewrite `chat` and `achat` to use them; apply `_map_error` in
      `astream_chat` too where it makes sense.
- [x] Run `test_ollama.py`; confirm no behavioral change.

### Item 4 [M2]: Agent code path silently drops request parameters
- **Source finding:** [MEDIUM] agent path ignores temperature/top_p/max_tokens/model/tools
- **Severity / Effort:** Medium / M
- **Depends on / conflicts with:** none
- **Verification:** Test asserting the chosen behavior (params honored, or
  rejected/documented) for the agent path in `routes/chat.py`.

## [Question]
Q-M2: When `ENABLE_AGENT_ORCHESTRATION=true`, `routes/chat.py:80-88` calls
`agent_service.achat(messages)` and drops `temperature`, `top_p`, `max_tokens`,
`tools`, and `model` (model is only used to label the response). The planner
and final-answer LLM calls always use `LLMConfig` defaults. Which behavior?
  (a) Thread generation kwargs (temperature/top_p/max_tokens/model) through
      `AgentService.achat` → `Planner.plan` and `_generate_final_answer`'s
      `achat` calls. (`tools` from the client is out of scope — the agent uses
      its own registry.)
  (b) Keep ignoring them but explicitly reject (400) or document that they are
      ignored in agent mode.
Recommended: (a) for generation params, and explicitly document that
client-supplied `tools` are ignored in agent mode (the registry governs tools).

## [Answer]
Follow your recommendation

- [x] (blocked on Q-M2) If (a): add generation-kwarg plumbing through
      `AgentService.achat` → `Planner.plan(..., **kwargs)` →
      `LLMService.achat(..., **kwargs)`, and pass kwargs into
      `_generate_final_answer`'s `self._llm.achat(...)`. Pass kwargs from
      `routes/chat.py` (reuse/adapt `build_llm_kwargs`).
- [x] (blocked on Q-M2) If (b): raise `UnsupportedFeatureError` for set params in
      agent mode, or document in README/route; no plumbing.
- [x] Add a test for the chosen behavior.

### Item 5 [M3]: Redundant / dead persistence layer (`CheckpointStore` dual-write, `SessionStore` unused)
- **Source finding:** [MEDIUM] redundant + dead persistence
- **Severity / Effort:** Medium / S
- **Depends on / conflicts with:** `CheckpointStore` is wired as a constructor arg
  across `service.py`, `graph.py`, `app.py` and **6 test files**; deleting it is
  invasive. `SessionStore` is only self-referenced + exported.
- **Verification:** Approval resume tests in `test_graph.py` still pass;
  `test_checkpoint_store.py` updated/removed consistent with the decision.

## [Question]
Q-M3: Two sub-decisions (audit open question #2):
  (a) `CheckpointStore`: resume currently restores from
      `approval_store.get(id).graph_state`; `_save_checkpoint` also writes to
      `CheckpointStore` but `.load`/`.delete` are never called. Make
      `CheckpointStore` the single source of truth (read from it on resume, drop
      the duplicate `ApprovalRecord.graph_state` write), OR delete
      `CheckpointStore` entirely (remove the constructor param everywhere +
      update the 6 test files + `test_checkpoint_store.py`)?
  (b) `SessionStore`: delete now (unused), or keep as intentional groundwork?
Recommended: (a) delete `CheckpointStore`'s dead dual-write but **keep the class
and constructor wiring** as the documented future store, only removing the
unused `.save` call in `_save_checkpoint` — least invasive; OR if you want it
gone, full delete. (b) delete `SessionStore`.
(Pick one of the (a) variants explicitly so I don't guess the blast radius.)

## [Answer]
Follow your recommendation


- [x] (blocked on Q-M3a) Apply the chosen `CheckpointStore` resolution (drop
      dead write / make authoritative / full delete + cascade through
      service/graph/app/tests).
- [x] (blocked on Q-M3b) If delete: remove `session_store.py`, drop it from
      `persistence/__init__.py` `__all__` and import.

### Item 6 [M4]: `errors` state field written but never surfaced; validation failure swallowed
- **Source finding:** [MEDIUM] `errors` field silent failure
- **Severity / Effort:** Medium / S
- **Depends on / conflicts with:** `AgentResponse` data model (public-ish).
- **Verification:** Test for the malformed-plan path (`selected_tool_call is
  None`) asserting the chosen behavior (surfaced error vs raised exception).

## [Question]
Q-M4: `AgentState.errors` is appended only in `_validate_tool_call` when
`selected_tool_call is None`, then the graph continues to a final answer with no
signal. Sibling failures in the same function `raise` (`ToolNotFound`,
`ToolValidationError`). Pick one consistent strategy:
  (a) Surface `errors` to the caller — add `errors: list[str]` to
      `AgentResponse` and populate it in `AgentService.achat`.
  (b) Remove the `errors` field entirely and `raise` consistently (e.g.
      `PlanningError`) in the `None` case like its siblings.
Recommended: (b) — raise consistently; the `errors` field is otherwise dead and
adds an unused public surface.

## [Answer]
Follow your recommendation


- [x] (blocked on Q-M4) Apply chosen strategy in `graph.py::_validate_tool_call`
      and (if (a)) `state.py`, `models.py::AgentResponse`, `service.py`.
- [x] Add a test for the malformed-plan path.

### Item 7 [M5]: Advertised iterative "agent loop" is single-step only
- **Source finding:** [MEDIUM] single-step loop vs docstring/diagram
- **Severity / Effort:** Medium / M (implement) or S (correct docs)
- **Depends on / conflicts with:** Drives Item 12 (L3 no-op nodes).
- **Verification:** If docs-only: review docstring/diagram against code. If
  implemented: new test showing two tool iterations in one run.

## [Question]
Q-M5: The module docstring/diagram (`graph.py:1-21`) shows a tool→decide loop,
but `_execute_tool` clears `plan`/`selected_tool_call`, so the loop never
iterates and the planner only ever returns one tool_call. Which?
  (a) Correct the docstring/diagram to reflect single-step execution (S, no
      behavior change).
  (b) Implement real re-planning after tool execution (M, adds a re-plan node
      and loop-exit conditions) — larger architecture change.
Recommended: (a) for this remediation pass; defer multi-step to a dedicated
feature task.

## [Answer]
Follow your recommendation


- [x] (blocked on Q-M5) If (a): update the `graph.py` module docstring/diagram to
      single-step. If (b): design + add re-planning node, iteration guard, and
      tests (larger scope — flag if chosen).

### Item 8 [M6]: Tool backends are inline stubs; agent feature non-functional when enabled
- **Source finding:** [MEDIUM] inline stub backends in `app.py:35-117`
- **Severity / Effort:** Medium / M
- **Depends on / conflicts with:** none directly; relates to M2/M5 scope.
- **Verification:** App still builds with agent orchestration enabled; stub
  behavior unchanged unless real backends chosen.

## [Question]
Q-M6: `_build_agent_service` defines five stub backend classes inline (empty
results / "not_configured"); no real Web/Gmail/Calendar backends exist in the
repo (audit open question #1). Which?
  (a) Extract the stubs to `agent_orchestration/tools/backends_stub.py` and
      select them via config — structural cleanup only, behavior unchanged.
  (b) Implement real backends (out of scope for a tech-debt pass; large).
  (c) Leave as-is (intentional placeholder wiring).
Recommended: (a) — extract stubs to a module + select via config; real backends
are a separate feature.

## [Answer]
Follow your recommendation


- [x] (blocked on Q-M6) If (a): move stub classes to `backends_stub.py`, remove
      nested defs + inline imports from `app.py`, wire via config.
- [x] (blocked on Q-M6) If (c): add a comment documenting the intentional stub
      wiring; no code move.

### Item 9 [M8]: No direct tests for tool implementations or the agent OpenAI adapter
- **Source finding:** [MEDIUM] test gap: tools + `agent_response_to_openai`
- **Severity / Effort:** Medium / S
- **Depends on / conflicts with:** Item 2 (H2) — failure-path tests assert the new
  graceful `ToolResult`. Item 1 (H1) timeout test also lands here.
- **Verification:** New tests added and passing.

- [x] Add per-tool tests (web_search, web_fetch, gmail, calendar) with fake
      backends covering success and the failure path (H2 behavior).
- [x] Add a test for `agent_orchestration/adapters/openai_adapter.py::agent_response_to_openai`.
- [x] Add the Ollama timeout-injection test from Item 1.

### Item 10 [M7]: No static type checking in CI
- **Source finding:** [MEDIUM] no mypy/pyright gate
- **Severity / Effort:** Medium / S (add job) + M (fix initial findings)
- **Depends on / conflicts with:** Adds a dependency + CI job.
- **Verification:** Type-check command passes locally and as a new CI job.

## [Question]
Q-M7: Add a static type-check gate? Choose tool and scope:
  (a) Add `mypy` (dev dep + `[tool.mypy]` config + CI job).
  (b) Add `pyright`/`basedpyright` (CI job).
  (c) Skip for this pass.
And: fix all initial findings now (M) or add the gate and triage findings
separately? Recommended: (a) mypy as a dev dep + CI job, run in a non-blocking
("informational") mode first OR fix the small initial set if low — your call on
strictness.

## [Answer]
Follow your recommendation


- [x] (blocked on Q-M7) Add the chosen type checker dev dep + config to
      `pyproject.toml`; add a CI job mirroring the lint job.
- [x] (blocked on Q-M7) Resolve or `# type: ignore`-justify initial findings to
      the agreed strictness.

### Item 11 [L1]: Stray empty top-level `tools/` package — **mechanical, ready**
- **Source finding:** [LOW] empty top-level `tools/__init__.py`
- **Severity / Effort:** Low / S
- **Verification:** `git grep "from tools"`/`import tools` shows no references;
  full test suite passes after deletion.
- [x] Delete the top-level `tools/` package (confirmed empty, unreferenced, not
      in the Docker image).

### Item 12 [L3]: Vestigial no-op graph nodes
- **Source finding:** [LOW] no-op `_validate_plan` / `_decide_next_step` / `_risk_check`
- **Severity / Effort:** Low / S
- **Depends on / conflicts with:** Item 7 (M5).
- **Verification:** Manual review; `test_graph.py` passes.
- [x] (conservative default, no question) Add a short comment on each no-op node
      stating it exists purely as a trace/diagram instrumentation anchor (the
      real decision lives in the router functions). Do **not** collapse them
      (keeps the trace/diagram intact). Revisit if M5 (b) is chosen.

### Item 13 [L4]: Tool arguments validated twice — **deferred**
- **Source finding:** [LOW] double validation (graph + `arun`)
- **Severity / Effort:** Low / S
- **Depends on / conflicts with:** Item 2 (H2): removing the graph-level
  pre-validation would turn bad-args (currently a clean 400 `ToolValidationError`)
  into a graceful `ToolResult(success=False)` under H2 — a behavior change; and
  passing the parsed model into `arun` changes the `BaseTool.arun` interface
  (all tools + tests). See "Out of scope / deferred".

### Item 14 [L5]: IDE config committed (`.idea/`) — **mechanical, ready**
- **Source finding:** [LOW] `.idea/` tracked
- **Severity / Effort:** Low / S
- **Verification:** `git ls-files | grep .idea` returns nothing after untracking.
- [x] `git rm --cached -r .idea/` (6 tracked files) and uncomment/add `.idea/`
      in `.gitignore` (line ~189 already has it commented).

### Item 15 [L6]: `default_model` configured in two places
- **Source finding:** [LOW] `LLMConfig.default_model` vs `APIServerConfig.default_model`
- **Severity / Effort:** Low / S
- **Verification:** Manual review of the documented precedence.
- [x] (conservative default, no question) Do **not** change the config format.
      Add a short comment/README note documenting precedence: the non-agent path
      uses `APIServerConfig.default_model` as a fallback to the request model;
      the agent path uses `LLMConfig.default_model`. (If you'd rather unify to a
      single owner, tell me and I'll add a [Question].)

### Item 16 [L7]: TRACE logging may leak nested sensitive data — **mechanical, ready**
- **Source finding:** [LOW] `redact()` doesn't recurse into lists/tuples
- **Severity / Effort:** Low / S
- **Verification:** New unit test: `redact()` on a list of dicts with sensitive
  keys redacts nested values.
- [x] Make `logging_utils.redact()` recurse into `list`/`tuple` (and continue to
      recurse dict values), preserving current str/dict behavior.
- [x] Add a `redact()` nested-structure test.

### Item 17 [L8]: No pytest/ruff config block; no coverage tooling — **mechanical, ready (with one sub-choice)**
- **Source finding:** [LOW] missing `[tool.pytest.ini_options]`, no coverage
- **Severity / Effort:** Low / S
- **Verification:** `uv run pytest` still green with `asyncio_mode = "auto"`.
- [x] Add `[tool.pytest.ini_options]` to `pyproject.toml` with
      `asyncio_mode = "auto"` (existing explicit markers remain compatible).
- [x] Add a minimal `[tool.ruff]` block capturing current effective settings
      (no rule changes — keep lint/format behavior identical to CI).
- [x] (optional) Add `pytest-cov` dev dep and a coverage report step. Note: a CI
      coverage *threshold* would gate builds — left out unless you want it (say
      so and I'll add a [Question] for the threshold).

---

## Out of scope / deferred

- **L4 (double validation):** deferred — the clean fix changes either error
  semantics (entangled with H2) or the `BaseTool.arun` interface (all tools +
  tests). Not worth the blast radius in this pass; revisit after H2 lands.
- **M5 (b) multi-step agent loop:** deferred unless explicitly chosen in Q-M5 —
  it's a feature, not debt cleanup.
- **M6 (b) real Web/Gmail/Calendar backends:** out of scope — feature work.
- **`test_debug_logging.py` size (525 LOC):** audit flagged it as worth a skim
  for over-mocking but did not line-audit it; not changed here.
- **README/DESIGN doc drift (audit open question #4):** not cross-checked here
  beyond the M5 docstring; can be a follow-up.
- **Working-tree noise:** `test.py` (Item L2 question), the `prompts/` renames,
  and `api_server/README.md` edits already present in the working tree are not
  touched except where a work item explicitly covers them.

## [Question]
Q-L2: `test.py` at repo root is a manual debug harness (live Ollama at import
time, not pytest-collected) and is **currently modified in your working tree**.
Because you're actively editing it, I won't delete it without confirmation.
Which?
  (a) Delete it.
  (b) Move it under `scripts/` (e.g. `scripts/manual_planner_check.py`).
  (c) Leave it (you're using it).
Recommended: (b) move to `scripts/` if it's still useful, else (a) delete.

## [Answer]
Follow your recommendation

