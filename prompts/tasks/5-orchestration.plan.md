# Implementation Plan: Agent Orchestration Module

## Summary

Implement a `agent_orchestration` module for Jarvis — a LangGraph-based personal AI agent that receives messages via the existing OpenAI-compatible API, plans tool use, validates and executes tools with approval gating, and returns grounded final answers.

Architecture:
```
Open WebUI
    ↓ OpenAI-compatible API
api_server
    ↓
agent_orchestration
    ├── llm   (planning + final answer)
    └── tools (tool execution)
```

All architecture review adjustments from `prompts/tmp/tmp.md` are incorporated:
- Tools are siblings of `llm`, not downstream
- Store abstractions introduced immediately (in-memory)
- LangGraph approval resume via explicit checkpoint serialisation
- Strict Pydantic validation before tool execution
- Deterministic risk classification only (LLM classifier disabled by default)
- Explicit streaming rejection when agent mode is on
- Interface-driven tool backends
- Final answer grounded on actual tool results
- Critical safety test: risky tool backend call count == 0 before approval

---

## Step 1 — Add `langgraph` dependency

- [x] Add `langgraph` to `[project]` dependencies in `pyproject.toml`
- [x] Run `uv lock` to update the lockfile

---

## Step 2 — Create `agent_orchestration/` skeleton

- [x] `agent_orchestration/__init__.py`
- [x] `agent_orchestration/exceptions.py` — typed exception hierarchy:
  `AgentError`, `PlanningError`, `ToolExecutionError`, `ToolNotFoundError`,
  `ToolValidationError`, `ApprovalRequiredError`, `ApprovalNotFoundError`,
  `CheckpointNotFoundError`
- [x] `agent_orchestration/models.py` — `AgentPlan`, `PendingToolCall`, `ToolResult`,
  `AgentResponse`, `ApprovalRequest`, `ApprovalDecision`

---

## Step 3 — Create `agent_orchestration/config.py`

- [x] `AgentConfig(BaseSettings)` with fields:
  - `agent_enabled: bool = True`
  - `require_approval_for_sensitive_read: bool = False`
  - `require_approval_for_external_write: bool = True`
  - `require_approval_for_destructive: bool = True`
  - `require_approval_for_unknown: bool = True`
  - `enable_llm_risk_classifier: bool = False`

---

## Step 4 — Create tool system (`agent_orchestration/tools/`)

- [x] `tools/__init__.py`
- [x] `tools/risk.py` — `ToolRiskLevel` enum: `SAFE_READ_ONLY`, `SENSITIVE_READ`,
  `EXTERNAL_WRITE`, `DESTRUCTIVE`, `UNKNOWN`
- [x] `tools/base.py` — abstract `BaseTool` with `name`, `description`, `risk_level`,
  `args_schema: type[BaseModel]`, `arun(arguments) -> ToolResult`
- [x] `tools/registry.py` — `ToolRegistry.register()`, `.get()`, `.list_tools()`
- [x] `tools/backends.py` — Protocol interfaces `WebSearchBackend`, `GmailBackend`,
  `CalendarBackend` plus all result models
  (`WebSearchResult`, `GmailMessageSummary`, `GmailMessage`, `GmailSendResult`,
  `CalendarEvent`, `CalendarEventCreate`, `CalendarEventUpdate`, `CalendarDeleteResult`)
- [x] `tools/web_search.py` — `WebSearchTool` (SAFE_READ_ONLY)
- [x] `tools/gmail.py` — `GmailSearchMessagesTool` (SENSITIVE_READ),
  `GmailReadMessageTool` (SENSITIVE_READ), `GmailSendEmailTool` (EXTERNAL_WRITE)
- [x] `tools/calendar.py` — `CalendarSearchEventsTool` (SENSITIVE_READ),
  `CalendarCreateEventTool` (EXTERNAL_WRITE), `CalendarUpdateEventTool` (EXTERNAL_WRITE),
  `CalendarDeleteEventTool` (DESTRUCTIVE)

---

## Step 5 — Create approval system (`agent_orchestration/approval/`)

- [x] `approval/__init__.py`
- [x] `approval/models.py` — `ApprovalStatus` enum (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`),
  `ApprovalRecord` dataclass with:
  `approval_id`, `conversation_id`, `graph_state: dict`, `pending_tool_call: PendingToolCall`,
  `risk_reason: str`, `created_at`, `expires_at | None`, `status: ApprovalStatus`
- [x] `approval/policy.py` — `ApprovalPolicy(config: AgentConfig)` with
  `requires_approval(risk_level: ToolRiskLevel) -> bool`
- [x] `approval/store.py` — `ApprovalStore` (in-memory dict, documented as not production-safe)

---

## Step 6 — Create persistence stubs (`agent_orchestration/persistence/`)

- [x] `persistence/__init__.py`
- [x] `persistence/session_store.py` — `SessionStore` (in-memory stub, not production-safe)
- [x] `persistence/checkpoint_store.py` — `CheckpointStore` (in-memory dict; stores
  serialised graph state keyed by `conversation_id` for approval resume; not production-safe)

---

## Step 7 — Create `agent_orchestration/state.py`

- [x] `AgentState(TypedDict)` with fields:
  `conversation_id`, `messages`, `user_request`, `plan`, `selected_tool_call`,
  `tool_results`, `approval_request`, `approval_decision`, `final_response`, `errors`

---

## Step 8 — Create planning module (`agent_orchestration/planning/`)

- [x] `planning/__init__.py`
- [x] `planning/prompts.py` — system prompt and user message templates for the planner
- [x] `planning/planner.py` — `Planner(llm_service: LLMService, registry: ToolRegistry)`:
  - Formats available tools into prompt context
  - Calls `LLMService.achat()` with `response_model=AgentPlan`
  - Validates structured output; raises `PlanningError` on failure

---

## Step 9 — Create `agent_orchestration/graph.py`

LangGraph `StateGraph` with the following nodes (all async):

- [x] `load_context` — initialise state from incoming messages
- [x] `classify_or_detect_approval` — regex-detect `APPROVE <id>` or `REJECT <id>`;
  route to `load_checkpoint` branch or `plan` branch
- [x] `load_checkpoint` — load serialised graph state from `CheckpointStore`;
  raise `CheckpointNotFoundError` if missing
- [x] `apply_approval_decision` — set `approval_decision` in state; if rejected, clear
  `selected_tool_call` and proceed to `generate_final_answer`
- [x] `plan` — call `Planner`; store `AgentPlan` in state
- [x] `validate_plan` — confirm plan is well-formed; error if malformed
- [x] `decide_next_step` — conditional: no tool needed → `generate_final_answer`;
  tool needed → `validate_tool_call`
- [x] `validate_tool_call` — confirm tool in registry + validate args schema;
  raise `ToolNotFoundError` / `ToolValidationError` on failure
- [x] `risk_check` — `ApprovalPolicy.requires_approval()`:
  safe → `execute_tool`; risky → `create_approval_request`
- [x] `execute_tool` — call `tool.arun()`; on error raise `ToolExecutionError`;
  append `ToolResult` to `tool_results`; loop back to `decide_next_step`
- [x] `create_approval_request` — build `ApprovalRequest`, format human-readable message,
  save in state
- [x] `save_checkpoint` — serialise current graph state to `CheckpointStore`
- [x] `return_approval_message` — set `final_response` to approval prompt text; END
- [x] `generate_final_answer` — call `LLMService.achat()` with tool results injected
  as explicit context; set `final_response`; END

Edges and conditional routing wired between all nodes.

---

## Step 10 — Create `agent_orchestration/service.py`

- [x] `AgentService(llm_service, registry, approval_store, checkpoint_store, config)`:
  - `achat(messages, tools_enabled, conversation_id, **kwargs) -> AgentResponse`
  - Build and run the LangGraph
  - Return `AgentResponse`

---

## Step 11 — Create `agent_orchestration/adapters/openai_adapter.py`

- [x] `agent_response_to_openai(response: AgentResponse, model: str) -> ChatCompletionResponse`
  — reuses OpenAI schema types from `api_server/schemas/openai.py`

---

## Step 12 — Integrate with `api_server`

- [x] Add `enable_agent_orchestration: bool = False` to `APIServerConfig`
- [x] Add `get_agent_service` dependency to `api_server/dependencies.py`
- [x] Update `api_server/app.py`:
  - Conditionally create `AgentService` and store on `app.state.agent_service`
- [x] Update `api_server/routes/chat.py`:
  - Agent mode + `stream=True` → raise `UnsupportedFeatureError` (agent streaming not supported)
  - Agent mode + `stream=False` → call `AgentService.achat()`, convert response
  - No agent mode → preserve existing `LLMService` paths unchanged
- [x] Update `api_server/errors.py` to register handlers for all `AgentError` subclasses

---

## Step 13 — Write unit tests (`tests/unit/agent_orchestration/`)

- [x] `__init__.py`
- [x] `test_config.py` — defaults and env-override loading
- [x] `test_exceptions.py` — exception hierarchy
- [x] `test_risk_policy.py` — all four risk levels × configurable approval
- [x] `test_tool_registry.py` — register, get, list, unknown → `ToolNotFoundError`
- [x] `test_approval_store.py` — save, load, status transitions
- [x] `test_checkpoint_store.py` — save and load round-trip
- [x] `test_planner.py` — valid plan, hallucinated tool rejected, invalid args rejected
- [x] `test_graph.py` (mocked LLMService + backends):
  - answer without tools
  - valid tool call plan → safe tool executes
  - sensitive read without approval (default config)
  - sensitive read requires approval when `require_approval_for_sensitive_read=True`
  - risky tool returns approval request; Gmail backend call count == 0
  - APPROVE reply resumes; Gmail backend call count == 1
  - REJECT reply skips; Gmail backend call count == 0
  - unknown tool raises `ToolNotFoundError`
  - tool execution failure raises `ToolExecutionError`
  - calendar delete requires approval
  - web search does not require approval
  - final answer grounded on tool results (mock results injected into final LLM call)
- [x] `test_agent_service.py` — service-level routing and response shaping
- [x] `test_api_integration.py`:
  - routes to `AgentService` when `ENABLE_AGENT_ORCHESTRATION=true`
  - routes to `LLMService` when disabled
  - `stream=true` with agent mode → 400 unsupported error

---

## Step 14 — Write documentation

- [x] `agent_orchestration/DESIGN.md`
- [x] `agent_orchestration/README.md`

---

## [Question]
`langgraph` is already in `uv.lock` (pulled in transitively by `langchain`) but is not listed in `pyproject.toml` `[project]` dependencies. Should it be added as an explicit runtime dependency, or left as an implicit transitive dependency?

My recommendation: add it explicitly in `[project]` dependencies because `agent_orchestration` imports it directly. This prevents it from disappearing if the `langchain` dependency tree changes.

## [Answer] add it explicitly in `[project]` dependencies

