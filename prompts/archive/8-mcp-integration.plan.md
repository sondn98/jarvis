# Plan: Integrate Jarvis with MCP Servers (task 8)

Task source: `prompts/tasks/8-mcp-integration.md`. This plan follows the task's
phased structure. **Phase 0 is complete (findings below). Phase 1 decisions are
open and require owner sign-off. No implementation (Phase 2) code will be written
until every Phase 1 question is answered.**

---

## Phase 0 — Codebase Discovery (findings, no code changes)

### 1. Framework / structure of `agent_orchestration`
- **Framework:** LangGraph (`langgraph>=0.2.0`) with LangChain (`langchain>=1.3.9`)
  declared as deps. The orchestration itself is a hand-built `StateGraph` in
  `agent_orchestration/graph.py` (592 LOC) — nodes + conditional edges, not a
  prebuilt LangChain agent executor.
- **LLM provider/SDK:** Local **Ollama** (`ollama>=0.6.2`), wrapped by a custom
  `llm` module (`llm/service.py` → `llm/providers/ollama.py`). Only an Ollama
  provider exists today.
- **How tools are surfaced to the model — IMPORTANT:** The agent does **not** use
  native/function-calling tool APIs. `agent_orchestration/planning/planner.py`
  renders tools to **plain text** (`format_tool_descriptions`: `- name: description
  (risk: level)`) inside `PLANNER_SYSTEM_PROMPT`, then asks the model for a
  structured JSON `AgentPlan` via `response_model=AgentPlan`. The model returns at
  most one `PendingToolCall{tool_name, arguments}`.
  - Note: `llm/models.py` *does* define `ToolDefinition`/`ToolCall` (native
    tool-calling types), but the agent planning path does not use them. This means
    MCP tool JSON-schemas do **not** have to be threaded into a provider
    tool-calling payload — surfacing name + description (+ maybe input schema) as
    text is sufficient for the current planner.
- **Tool definition pattern:** `agent_orchestration/tools/base.py` —
  `BaseTool(ABC)` with class attrs `name: str`, `description: str`,
  `risk_level: ToolRiskLevel`, `args_schema: type[BaseModel]`, and
  `async arun(arguments: dict) -> ToolResult`. Each tool wraps a backend Protocol
  (`backends.py`).
- **Registry:** `agent_orchestration/tools/registry.py` — `ToolRegistry`, a
  `dict[str, BaseTool]` keyed by `tool.name`, with `register/get/list_tools`.
- **Dispatch logic:** in `graph.py`:
  - `_plan` → planner produces `selected_tool_call`.
  - `_validate_tool_call` → `registry.get(name)` then `tool.args_schema(**arguments)`.
  - `_risk_check` → `ApprovalPolicy.requires_approval(tool.risk_level)` (may route
    to human approval + checkpoint/resume).
  - `_execute_tool` → `registry.get(name)`, `await tool.arun(arguments)`, wraps
    result/exception into `ToolResult`.
  - Execution is **single-step** (one tool per request; no re-planning loop).

### 2. Current tool inventory (9 tools, all backed by stubs)
| Tool name | File | ~LOC |
|---|---|---|
| `web_search` | `tools/web_search.py` | 38 |
| `web_fetch` | `tools/web_fetch.py` | 36 |
| `gmail_search_messages`, `gmail_read_message`, `gmail_send_email` | `tools/gmail.py` | 93 |
| `calendar_search_events`, `calendar_create_event`, `calendar_update_event`, `calendar_delete_event` | `tools/calendar.py` | 134 |
| (Backend protocols) | `tools/backends.py` | 106 |
| (Stub backends — return `[]` / `not_configured`) | `tools/backends_stub.py` | 79 |
| (`BaseTool`, `ToolRegistry`, `ToolRiskLevel`) | `tools/base.py`, `registry.py`, `risk.py` | 17 / 19 / 9 |

All backends are **stubs only** (`agent_backend="stub"` is the only supported
value; `api_server/app.py::_build_tool_registry` hard-errors otherwise). There is
no real Web/Gmail/Calendar integration — these are prototypes proving the loop, as
the task states.

### 3. Config / secrets handling
- **Mechanism:** `pydantic-settings` `BaseSettings`, one class per module, all
  reading env vars + the project-root `.env` (`SettingsConfigDict(env_file=".env",
  extra="ignore")`):
  - `llm/config.py` → `LLMConfig`
  - `api_server/config.py` → `APIServerConfig`
  - `agent_orchestration/config.py` → `AgentConfig`
- **No file-based / JSON config exists today.** Current `.env` keys:
  `DEFAULT_MODEL`, `ENABLE_AGENT_ORCHESTRATION`, `LOG_LEVEL`, `OLLAMA_BASE_URL`.
- **Implication:** an MCP `mcpServers` JSON config file would be a *new* convention
  (no existing JSON config to follow), but the *path/enable flag* for it can follow
  the existing env-var convention (e.g. an env var pointing at the JSON file). This
  is a Phase 1 decision (Q4).

### 4. Runtime environment
- **Long-lived server process:** `main.py` → `api_server.app.create_app()` →
  `uvicorn.run(app, ...)`. FastAPI app exposing an OpenAI-compatible API
  (`/v1/chat/completions`, etc.). Also Dockerized (`Dockerfile`).
- **Implication:** Both **stdio subprocesses** (spawn + keep alive for the process
  lifetime) and **persistent HTTP/SSE connections** are technically viable. Agent
  services are built once at startup (`create_app`) and held on `app.state`, so a
  startup-time connection lifecycle fits the existing shape cleanly.

### 5. Relevant existing dependencies
- **No MCP SDK installed** — `mcp` is absent from `uv.lock`. Nothing MCP-adjacent
  present.
- `httpx>=0.28.1` is already a dependency (relevant if HTTP transport is chosen).

---

## Phase 1 — Architecture Decisions (OPEN — owner sign-off required)

For each question I give a recommendation with reasoning, but **I will not pick.**
Please fill in each `## [Answer]` block.

### Q1 — Transport support

## [Question]
Which MCP transport(s) should v1 support: local **stdio** subprocesses, **remote
HTTP/SSE (Streamable HTTP)**, or both?
- Context: Jarvis runs as a long-lived server process, so both are technically
  viable. stdio favors local dev tools (filesystem, git, sqlite); HTTP favors
  hosted services. The reference MCP servers (e.g. `@modelcontextprotocol/server-*`)
  are mostly stdio.
- Options:
  - (a) **stdio only** — simplest first version, matches most reference servers,
    no network/auth surface. (Recommended for v1.)
  - (b) **HTTP/SSE only** — if your intended servers are hosted/remote.
  - (c) **Both** — maximum flexibility, but more surface to build/test for a first
    cut (risk of over-engineering v1).
- I need your actual use case to recommend confidently: are the MCP servers you
  intend to connect to **local developer tools** or **hosted/remote services**?

## [Answer]
I intend to connect to mcp servers for remote services, like Gmail, Calendar, ... So I prefer HTTP/SSE only. Jarvis is deployed on a k8s pod so local resources do not provide so much value

### Q2 — MCP client library

## [Question]
Use the official `mcp` Python SDK, or a custom/alternative client?
- Recommendation: **official `mcp` SDK** — it's the reference implementation, keeps
  protocol/version handling out of our codebase (aligns with the owner's goal of
  *not* maintaining tool plumbing), and supports both stdio and HTTP transports. A
  custom client only makes sense if we want zero new deps, which doesn't seem worth
  it here.
- Do you approve adding `mcp` as a dependency, or is there a constraint (offline
  builds, dependency policy) I should know about?

## [Answer]
Follow your recommendation

### Q3 — Integration point in the orchestration loop

## [Question]
How should MCP-discovered tools be surfaced to the existing dispatch logic?
- (a) **Adapter layer (Recommended):** wrap each MCP tool in a `BaseTool` subclass
  (`MCPTool`) whose `arun` calls the MCP client's `call_tool`, and register it in
  the existing `ToolRegistry`. The planner already renders tools from the registry
  as text, and `args_schema` can be built from the MCP tool's JSON input schema.
  **Lowest disruption** — graph dispatch, risk-check, approval, and final-answer
  paths are untouched.
  - Sub-question: MCP tools have no risk classification. Default all MCP tools to a
    fixed `ToolRiskLevel` (e.g. `UNKNOWN`, which currently triggers approval per
    `require_approval_for_unknown=True`), or map by a per-server config field?
- (b) **MCP-native rewrite:** replace `BaseTool`/registry with an MCP-native
  abstraction. Bigger refactor, removes a translation layer, but discards working
  approval/risk machinery. Not recommended given current coupling is low and the
  adapter is cheap.

## [Answer]
Option (a) is good. Default all MCP tools to `UNKNOWN` and make the risk classification of each tool configurable

### Q4 — Server configuration format & location

## [Question]
The owner has specified a JSON config file like Claude Desktop's `mcpServers`.
Please confirm three sub-decisions:
- **(4a) Location:** options — `~/.jarvis/mcp_servers.json` (XDG/home, per-user),
  project-root `mcp_servers.json`, or a path given by a new env var
  `MCP_CONFIG_PATH` (Recommended: env var with a sensible default, since all
  current config is env-driven — keeps one convention).
- **(4b) Secrets/env for MCP servers:** inline in the JSON like Claude Desktop
  (`"env": {"API_KEY": "..."}`), or referenced from the existing `.env`/env-var
  mechanism (e.g. `"env": {"API_KEY": "${SOME_ENV}"}` expansion)? (Recommended:
  support `${VAR}` expansion from the process environment so secrets stay in `.env`,
  not committed JSON.)
- **(4c) Load timing:** load once at startup only, or support hot-reload / runtime
  add-remove of servers? (Recommended: **load once at startup** for v1; hot-reload
  is a later feature.)

## [Answer]
Json file should be specified by a path given by a new env var `MCP_CONFIG_PATH` and is loaded once at startup only

### Q5 — Connection lifecycle & failure handling

## [Question]
- **(5a) When to connect:** at **startup** (connect all configured servers, list
  their tools, register them) or **lazily** on first tool use? (Recommended:
  startup — fits `create_app` wiring and lets the planner see the full tool list.)
- **(5b) On a server that's unreachable / fails to initialize:** fail Jarvis
  startup entirely, or **skip that server with a warning and continue** with the
  rest? (Recommended: skip-with-warning, so one bad server doesn't take down the
  agent.) Any retry policy desired, or is log-and-skip enough for v1?

## [Answer]
Connect mcp on the first tool use. On a unreachable initialization, skip that server with a warning and continue

### Q6 — Tool name collisions

## [Question]
If two MCP servers expose the same tool name, or an MCP tool name collides with a
remaining built-in tool, how should it resolve?
- (a) **Namespacing by server** — register as `<server>.<tool>` (or
  `<server>__<tool>`). Deterministic, no silent shadowing. (Recommended.)
- (b) **First-wins / last-wins** with a warning.
- (c) **Hard error at load time.**
Note: namespacing changes the tool name the planner sees and the model must emit —
acceptable since names are only surfaced as text. Please confirm the separator if
you choose (a).

## [Answer]
Option (a)

### Q7 — Disposition of existing prototype tools

## [Question]
Once MCP integration works end-to-end, do you approve removing the prototype tools,
and if so which? Candidate removals (no deletion until you say so here):
- `tools/web_search.py`, `web_fetch.py`, `gmail.py`, `calendar.py`,
  `backends.py`, `backends_stub.py`, and their registration block in
  `api_server/app.py` (+ the `agent_backend="stub"` plumbing in
  `agent_orchestration/config.py`).
- Keep `BaseTool`, `ToolRegistry`, `ToolRiskLevel`, `risk.py` (reused by the MCP
  adapter).
Options: (a) remove all prototype tools once MCP is live; (b) keep them behind the
`agent_backend` flag as a fallback; (c) decide per-tool later.
**This stays unchecked and untouched until explicit go-ahead (task Phase 2 step 6).**

## [Answer]
Option (a) - remove all prototype tools once MCP is live

---

## Phase 2 — Implementation checklist (DO NOT START until Phase 1 answered)

Steps are contingent on the answers above; details (transport, config path,
namespacing) will be finalized once decisions land. Natural checkpoint after each
step for owner test/review.

- [x] **2.0** Re-confirm all Phase 1 answers are filled in; adjust steps below to
  match the chosen options.

  **Consolidated decisions (locked):**
  - Q1: **Streamable HTTP transport only** (no stdio). Servers are remote; Jarvis runs on k8s.
  - Q2: Official **`mcp`** Python SDK.
  - Q3: **Adapter** `MCPTool(BaseTool)` registered into existing `ToolRegistry`.
    Risk: default **`UNKNOWN`**, overridable per server / per tool via config.
  - Q4: Config is a JSON file at path from **`MCP_CONFIG_PATH`** env var, **parsed once at
    startup**. Secrets via **`${VAR}` expansion** from process env (flagged reversible — owner
    didn't explicitly answer 4b; chose the security-safe default so secrets stay in `.env`).
  - Q5: **Lazy connect on first agent request** (not at app boot); unreachable server →
    **skip with warning** and continue. Log-and-skip (no retry) for v1.
  - Q6: **Namespacing `<server>.<tool>`** (separator `.`; flagged minor — change if undesired).
  - Q7: After MCP is live end-to-end, **remove all prototype tools** (step 2.6).

  **Reconciliation note (Q4c parse-at-startup vs Q5a connect-on-first-use):** the planner
  needs the tool list to choose a tool, and discovery needs a connection. Resolution: the
  JSON config is *parsed* at startup; the *first agent request* triggers one-time lazy
  discovery+connection across configured servers (cached for the process lifetime). No MCP
  connections are made at app boot. Tool invocation opens a fresh Streamable-HTTP session per
  call (robust to mid-session server crashes; natural for stateless HTTP).
- [x] **2.1** Added `mcp==1.28.0` to `pyproject.toml`/`uv.lock`. Connection client
  `agent_orchestration/mcp/client.py` (Streamable HTTP: `list_tools`, `call_tool`,
  `render_tool_result`). Manual connectivity script `scripts/manual_mcp_check.py`
  (owner-run checkpoint against a real server).
- [x] **2.2** JSON config loader `agent_orchestration/mcp/config.py`
  (`MCPServerConfig`/`MCPConfig`/`load_mcp_config`): `mcpServers` shape, `${VAR}`
  expansion, `MCP_CONFIG_PATH` wiring via `AgentConfig.mcp_config_path`. Unit tests
  in `tests/.../mcp/test_config.py`.
- [x] **2.3** Adapter `agent_orchestration/mcp/adapter.py`: `MCPTool(BaseTool)`
  builds `args_schema` from the tool's JSON inputSchema, appends the schema to the
  description (so the text-based planner sees the args), assigns configurable risk
  (default `UNKNOWN`), and `arun` calls the MCP client. Unit tests in
  `test_adapter.py`.
- [x] **2.4** Multi-server support via `agent_orchestration/mcp/manager.py`
  (`MCPManager.ensure_ready`): lazy, idempotent discovery on first request;
  `<server>.<tool>` namespacing (Q6); registers into the existing `ToolRegistry`.
  Wired through `AgentService` (calls `ensure_ready` before each run) and
  `api_server/app.py::_build_mcp_manager`. Unit tests in `test_manager.py`.
- [x] **2.5** Error handling: unreachable server → skipped with warning at discovery
  (`MCPManager`); connection failure / `isError` / mid-session crash during a call →
  surfaced as a failed `ToolResult` (`MCPTool.arun`), so the graph's existing
  degrade-gracefully path applies; per-server `timeout` for connect/call. Covered by
  adapter + manager tests.
- [x] **2.6** Owner confirmed MCP works end-to-end. Executed Q7 removal: deleted
  `tools/web_search.py`, `web_fetch.py`, `gmail.py`, `calendar.py`, `backends.py`,
  `backends_stub.py`, their `test_tools.py`, and the orphaned
  `scripts/manual_planner_check.py`. Removed the `_build_tool_registry` stub block +
  tool imports from `api_server/app.py` (registry now starts empty, populated by
  MCP) and the `agent_backend` field from `AgentConfig`. Kept `BaseTool`,
  `ToolRegistry`, `risk.py`. Fixed `test_graph.py`'s lone `backends` import (local
  model stand-in). Refreshed `agent_orchestration/DESIGN.md` and `README.md` to
  describe the MCP tool source. Ruff clean; no new mypy errors; full suite green
  except 12 pre-existing env-dependent failures (live-LLM / `DEFAULT_MODEL`).

---

## Notes / flagged assumptions (reversible)
- Assumption: MCP tool descriptions surfaced as **text to the planner** (not native
  function-calling) is acceptable, because that's how the current planner already
  works. Reversible if you later want native tool-calling — flag if you want this
  reconsidered now.
- Assumption: the MCP adapter reuses the existing risk/approval machinery rather
  than bypassing it. Reversible via Q3.
