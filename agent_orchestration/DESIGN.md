# agent_orchestration — Design Document

## Summary

`agent_orchestration` is a LangGraph-based personal AI agent module for Jarvis. It receives user messages through the existing OpenAI-compatible API, plans whether tools are needed, validates and executes tools with risk-based approval gating, and returns grounded final answers — all without callers changing their integration.

---

## Architecture

```
Open WebUI
    ↓ OpenAI-compatible API
api_server
    ↓
agent_orchestration
    ├── llm   (planning + final answer generation)
    └── tools (tool execution)
```

`llm` is the only provider-facing module. `agent_orchestration` never calls Ollama or any provider SDK directly. `api_server` remains thin.

---

## Module Structure

```
agent_orchestration/
  __init__.py
  DESIGN.md
  README.md
  config.py          AgentConfig (pydantic-settings)
  exceptions.py      Typed exception hierarchy
  models.py          AgentPlan, PendingToolCall, ToolResult, AgentResponse, ApprovalRequest, ApprovalDecision
  state.py           AgentState (TypedDict for LangGraph)
  graph.py           AgentGraph — LangGraph workflow
  service.py         AgentService — public entry point

  planning/
    planner.py       Planner — calls LLM with structured output
    prompts.py       System/user prompt templates

  approval/
    models.py        ApprovalRecord, ApprovalStatus
    policy.py        ApprovalPolicy — deterministic risk check
    store.py         ApprovalStore (in-memory)

  persistence/
    checkpoint_store.py  CheckpointStore (in-memory)
    session_store.py     SessionStore (in-memory)

  tools/
    risk.py          ToolRiskLevel enum
    base.py          BaseTool (ABC)
    registry.py      ToolRegistry

  mcp/               MCP client integration (tools come from MCP servers)
    config.py        MCPServerConfig/MCPConfig + load_mcp_config (mcpServers JSON)
    client.py        Streamable HTTP connect / list_tools / call_tool
    adapter.py       MCPTool(BaseTool) — wraps an MCP tool as a BaseTool
    manager.py       MCPManager — lazy discovery + registration on first use

  adapters/
    openai_adapter.py  AgentResponse → OpenAI ChatCompletionResponse
```

---

## LangGraph Workflow

```
START
  ↓
load_context
  ↓
classify_or_detect_approval
  ├── APPROVE/REJECT <id> → load_checkpoint → apply_approval_decision
  │                           ├── approved → execute_tool → decide_next_step
  │                           └── rejected → generate_final_answer → END
  └── normal request → plan → validate_plan → decide_next_step
                                  ├── no tool → generate_final_answer → END
                                  └── tool    → validate_tool_call → risk_check
                                                   ├── safe  → execute_tool → decide_next_step (loop)
                                                   └── risky → create_approval_request
                                                                 → save_checkpoint
                                                                 → return_approval_message → END
```

---

## State Model

```python
class AgentState(TypedDict):
    conversation_id: str
    messages: list[Message]
    user_request: str | None
    plan: AgentPlan | None
    selected_tool_call: PendingToolCall | None
    tool_results: list[ToolResult]
    approval_request: ApprovalRequest | None
    approval_decision: ApprovalDecision | None
    final_response: str | None
    errors: list[str]
    _approval_detected: dict | None  # internal routing hint
```

---

## Planning Flow

1. `Planner` formats available tools and conversation history into a prompt.
2. Calls `LLMService.achat()` with `response_model=AgentPlan`.
3. Validates structured output with Pydantic.
4. Raises `PlanningError` if LLM fails or output is malformed.
5. Returns `AgentPlan(requires_tool, tool_call, final_answer, reasoning_summary)`.

---

## Tool Validation Flow

Before any tool executes, in this order:

1. Planner structured output validated via Pydantic (`AgentPlan`).
2. Tool name exists in `ToolRegistry` — raises `ToolNotFoundError` otherwise.
3. Tool argument schema validated via `tool.args_schema(**arguments)` — raises `ToolValidationError` otherwise.
4. Risk level evaluated by `ApprovalPolicy`.
5. If approval required: graph saves checkpoint, returns approval message, and ends.
6. If safe: tool executes via `tool.arun(arguments)`.

---

## Tool Source: MCP Servers

Tools are supplied by external MCP (Model Context Protocol) servers rather than
implemented in-tree. The registry starts empty; on the first agent request,
`MCPManager.ensure_ready` connects to each server configured in the `MCP_CONFIG_PATH`
JSON file (Streamable HTTP), lists its tools, and registers each as an `MCPTool`
(a `BaseTool` adapter) under the namespaced name `<server>.<tool>`. A server that is
unreachable is skipped with a warning. The graph and planner are unchanged — they
still consume `BaseTool` instances from the `ToolRegistry`. See
`agent_orchestration/mcp/` and the project README for the config format.

---

## Risk Policy

Risk levels (deterministic, encoded in tool metadata):

| Level | Default approval required |
|---|---|
| `SAFE_READ_ONLY` | No |
| `SENSITIVE_READ` | No (configurable) |
| `EXTERNAL_WRITE` | Yes |
| `DESTRUCTIVE` | Yes |
| `UNKNOWN` | Yes |

`SENSITIVE_READ` note: operations like `gmail_read_message` and `calendar_search_events` expose private user data. Set `require_approval_for_sensitive_read=True` for stricter privacy control.

LLM-based risk classification is not used in V1. `enable_llm_risk_classifier` exists as a config flag but has no effect.

---

## Approval and Resume Flow

LangGraph does not stay running between HTTP requests. The approval flow works through serialised state:

**Request #1 — risky tool detected:**
1. `risk_check` routes to `create_approval_request`.
2. `save_checkpoint` stores the full `AgentState` dict in `ApprovalStore` and `CheckpointStore`, keyed by `approval_id` and `conversation_id`.
3. `return_approval_message` sets `final_response` to the human-readable approval prompt.
4. Graph ends. HTTP response returns the approval prompt to the user.

**Request #2 — user replies `APPROVE <id>` or `REJECT <id>`:**
1. `classify_or_detect_approval` detects the approval pattern.
2. `load_checkpoint` retrieves the stored `ApprovalRecord` from `ApprovalStore`.
3. `apply_approval_decision` updates approval status and sets `approval_decision` in state.
4. If approved: `execute_tool` runs the tool, then loops to `decide_next_step`.
5. If rejected: goes directly to `generate_final_answer` which acknowledges the rejection.

---

## Store Abstractions

All stores have in-memory implementations only.

```python
class ApprovalStore    # saves/loads ApprovalRecord by approval_id
class CheckpointStore  # saves/loads graph state by conversation_id
class SessionStore     # conversation metadata (currently unused)
```

**WARNING**: All stores are not production-safe:
- State is lost on process restart.
- Not safe for multi-worker deployments.

Future implementations may use PostgreSQL, Redis, or SQLite by implementing the same interface.

---

## API Integration

Config flag in `APIServerConfig`:
```
ENABLE_AGENT_ORCHESTRATION=true   # default: false
```

Routing in `POST /v1/chat/completions`:

| Condition | Behaviour |
|---|---|
| Agent enabled, `stream=false` | Routes to `AgentService.achat()` |
| Agent enabled, `stream=true` | Returns `400 unsupported_feature` |
| Agent disabled, any | Existing `LLMService` behaviour unchanged |

---

## Streaming Limitation

Agent orchestration does not support streaming in V1.

When `"stream": true` is requested with agent mode enabled, the server returns:
```json
{
  "error": {
    "type": "unsupported_feature",
    "message": "Agent orchestration does not support streaming yet."
  }
}
```

This is deterministic. The server never fakes token streaming or silently buffers.

Existing direct LLM streaming (`ENABLE_AGENT_ORCHESTRATION=false`) is unaffected.

---

## Debug Logging

### Logger hierarchy

```
jarvis.agent           root agent logger
jarvis.agent.graph     graph node instrumentation (start/complete/duration/state transitions)
jarvis.agent.planner   planner decisions and LLM calls
jarvis.agent.tools     tool selection, arguments, results, duration
jarvis.agent.approval  approval requests, decisions, checkpoint state
```

### INFO behavior (default)

Only operational metadata is logged at INFO and above:

```
Received chat request
Selected provider / model
Tool execution started / completed
Request completed
```

No prompt content, tool arguments, or response text is logged at INFO.

### DEBUG behavior

```
jarvis.agent.graph:    Node started / completed / duration for every node
jarvis.agent.planner:  User request (truncated), planner decision (requires_tool, tool_name)
jarvis.agent.tools:    Tool selected, arguments, execution duration
jarvis.agent.approval: Approval requested (id, tool, risk level), decision (approved/rejected)
```

Example:
```
[DEBUG] jarvis.agent.planner  Planner decision: requires_tool=True, tool=web_search
[DEBUG] jarvis.agent.tools    Tool selected: web_search
[DEBUG] jarvis.agent.tools    Tool execution complete: web_search, duration: 120ms
[DEBUG] jarvis.agent.approval Approval requested: id=abc123, tool=send_email, risk_level=EXTERNAL_WRITE
```

### TRACE behavior

```
jarvis.agent.graph:    State before node, state after node, state diff (changed keys)
jarvis.agent.planner:  Full planner messages, raw LLM response, validated plan JSON
jarvis.agent.tools:    Full tool request payload, full tool response
jarvis.agent.approval: Pending tool call dict, checkpoint state, stored/resumed graph state
```

Example:
```
[TRACE] jarvis.agent.graph  State before plan: {'conversation_id': 'x', 'messages': [...], ...}
[TRACE] jarvis.agent.graph  State diff plan: {'plan': 'NoneType -> AgentPlan', ...}
```

### Lazy logging

All call sites use `%s`-style formatting:
```python
logger.debug("Planner decision: requires_tool=%s, tool=%s", plan.requires_tool, tool_name)
```

### Sensitive data redaction

Redaction is applied globally via `logging_utils.RedactionFilter`. Email addresses, bearer tokens, API keys, passwords, and cookies are masked before any log handler emits the record. Redaction is enabled by default and can be disabled via `REDACT_SENSITIVE_DATA=false`.

---

## Known Limitations

1. **In-memory stores only** — all state is lost on restart. Not safe for multi-worker.
2. **No streaming** — agent mode returns an error on `stream=true`.
3. **Single tool per plan** — the planner selects one tool per round. Multi-step planning loops back to `decide_next_step` after each tool result.
4. **MCP tools only** — all tools come from configured MCP servers; none are built in. With no `MCP_CONFIG_PATH` configured, the agent has no tools and answers directly.
5. **No persistent memory** — conversation history is not stored between sessions.
6. **Approval IDs are hex UUIDs** — they must be copied exactly into the reply. No fuzzy matching.
7. **LLM risk classifier disabled** — `enable_llm_risk_classifier=True` has no effect in V1.

---

## Future Extension Points

- **Persistent stores**: implement `ApprovalStore`, `CheckpointStore`, `SessionStore` against PostgreSQL/Redis/SQLite.
- **More MCP servers**: add entries to the `MCP_CONFIG_PATH` JSON file; tools are discovered and registered automatically on next startup.
- **Agent streaming**: stream reasoning updates and final answer chunks via `stream=true`.
- **Memory**: add `MemoryRetriever` / `MemoryWriter` in the `load_context` node.
- **LLM risk classifier**: enable via `enable_llm_risk_classifier=True` and implement a classifier node.
- **Multi-tool plans**: extend `AgentPlan` to carry a sequence of tool calls.
- **New tools**: implement `BaseTool`, register in `ToolRegistry`. No graph changes needed.
