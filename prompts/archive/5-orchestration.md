# Task: Implement Agent Orchestration Module

You are a senior AI/software engineer. Implement a new `agent_orchestration` module for the Jarvis AI Agent system.

Before starting, read the existing design documents `DESIGN.md` in:

* `llm/` module
* `api_server/` module

Also read the architecture review file and apply its required adjustments.

## Goal

Implement a **LangGraph + LangChain based personal AI agent orchestration module**.

The agent should:

1. Receive user messages through the existing OpenAI-compatible API.
2. Plan whether tools are needed.
3. Use the existing `llm` module for all model calls.
4. Use tool interfaces for web search, Gmail, and calendar operations.
5. Execute safe tools directly.
6. Pause before risky tools and request user approval.
7. Resume pending tool execution after user approval.
8. Return final answers through the existing `/v1/chat/completions` endpoint.
9. Keep memory/session persistence as extension points only for now.

## Correct Target Architecture

Use this conceptual architecture:

```text
Open WebUI
    ↓ OpenAI-compatible API
api_server
    ↓
agent_orchestration
    ├── llm
    └── tools
```

Do **not** model tools as downstream of the LLM.

Responsibilities:

* Planner uses `llm`.
* Final answer generator uses `llm`.
* Tool executor uses `tools`.
* Orchestrator coordinates planning, risk checks, approvals, tool execution, and final response generation.

## Existing Boundaries

Respect these constraints:

* `llm` remains the only provider-facing module.
* `agent_orchestration` must never call Ollama or provider SDKs directly.
* `api_server` must remain thin.
* The public API must remain OpenAI-compatible.
* Do not create a separate public agent endpoint unless absolutely unavoidable.
* Do not implement persistent memory yet.
* Do not hardcode secrets.
* Do not execute risky actions without approval.

## Required Module Structure

Create a new top-level module:

```text
agent_orchestration/
  __init__.py
  DESIGN.md
  README.md

  config.py
  models.py
  exceptions.py

  graph.py
  service.py
  state.py

  planning/
    __init__.py
    planner.py
    prompts.py

  approval/
    __init__.py
    policy.py
    models.py
    store.py

  persistence/
    __init__.py
    session_store.py
    checkpoint_store.py

  tools/
    __init__.py
    base.py
    registry.py
    risk.py
    backends.py
    web_search.py
    gmail.py
    calendar.py

  adapters/
    __init__.py
    openai_adapter.py
```

You may adjust filenames if needed, but keep the design modular.

## Core Services

### AgentService

Create a public service class:

```python
class AgentService:
    async def achat(
        self,
        messages: list[Message],
        tools_enabled: bool = True,
        conversation_id: str | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        ...
```

Responsibilities:

* Accept internal `llm.Message` objects.
* Detect approval/rejection replies.
* Start or resume the LangGraph workflow.
* Use `LLMService` for all LLM calls.
* Use `ToolRegistry` for tool lookup.
* Use `ApprovalPolicy` before tool execution.
* Use stores for approval/session/checkpoint state.
* Return an `AgentResponse`.

## Required Store Abstractions

Introduce these abstractions immediately, even if only in-memory implementations are provided:

```python
class SessionStore:
    ...

class CheckpointStore:
    ...

class ApprovalStore:
    ...
```

For now:

* Implement in-memory versions.
* Clearly document that they are not production-safe.
* Do not assume state survives process restart.
* Do not assume multi-worker compatibility.

Future persistent implementations may use PostgreSQL, Redis, or SQLite.

## Approval Resume Design

LangGraph must not assume a continuously running graph across HTTP requests.

When risky tool execution is requested, store:

```python
approval_id
conversation_id
graph_state
pending_tool_call
risk_reason
created_at
expires_at | None
status
```

Workflow:

```text
Request #1
→ user asks task
→ planner selects risky tool
→ risk policy blocks execution
→ approval request is returned
→ graph state is saved

Request #2
→ user replies APPROVE <approval_id> or REJECT <approval_id>
→ approval store loads saved state
→ graph resumes from stored state
→ if approved, tool executes
→ if rejected, tool is skipped
→ final answer is generated
```

Approval replies must be normal chat messages so the system remains compatible with Open WebUI.

Example approval message:

```text
I need your approval before doing this:

Tool: gmail_send_email
Action: Send an email
Arguments:
{
  "to": "alice@example.com",
  "subject": "Meeting follow-up"
}

Risk: This sends an external email from your account.
Expected effect: An email will be sent from your Gmail account.

Reply with:
APPROVE <approval_id>
or
REJECT <approval_id>
```

## LangGraph Workflow

Implement a graph similar to:

```text
START
  ↓
load_context
  ↓
classify_or_detect_approval
  ├── approval reply → load_checkpoint → apply_approval_decision
  └── normal request → plan
  ↓
validate_plan
  ↓
decide_next_step
  ├── no tool needed → generate_final_answer → END
  └── tool needed → validate_tool_call
  ↓
risk_check
  ├── safe → execute_tool → observe_result → decide_next_step
  └── risky → create_approval_request → save_checkpoint → return_approval_message → END
```

Important:

* `WAIT_FOR_USER` is conceptual only.
* The graph must end after returning an approval request.
* A later HTTP request resumes from stored checkpoint state.

## Agent State

Create a typed LangGraph state.

Suggested model:

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
```

## Strict Planning and Tool Validation

Planner output must use strict Pydantic models.

Suggested models:

```python
class AgentPlan(BaseModel):
    requires_tool: bool
    tool_call: PendingToolCall | None = None
    final_answer: str | None = None
    reasoning_summary: str | None = None

class PendingToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
```

Before execution, validate in this order:

1. Planner structured output validation.
2. Tool name exists in `ToolRegistry`.
3. Tool argument schema validation.
4. Risk evaluation.
5. Approval check if required.
6. Tool execution.

The agent must reject hallucinated tools and invalid arguments.

## Tool System

Create a base tool interface:

```python
class BaseTool(ABC):
    name: str
    description: str
    risk_level: ToolRiskLevel
    args_schema: type[BaseModel]

    @abstractmethod
    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        ...
```

Create a registry:

```python
class ToolRegistry:
    def register(self, tool: BaseTool) -> None:
        ...

    def get(self, name: str) -> BaseTool:
        ...

    def list_tools(self) -> list[BaseTool]:
        ...
```

## Backend Interfaces

Tools must depend on backend interfaces, not concrete implementations.

Create:

```python
class WebSearchBackend(Protocol):
    async def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        ...

class GmailBackend(Protocol):
    async def search_messages(self, query: str, max_results: int = 10) -> list[GmailMessageSummary]:
        ...
    async def read_message(self, message_id: str) -> GmailMessage:
        ...
    async def send_email(self, to: str, subject: str, body: str, cc: str | None = None) -> GmailSendResult:
        ...

class CalendarBackend(Protocol):
    async def search_events(self, query: str | None, time_min: str | None, time_max: str | None) -> list[CalendarEvent]:
        ...
    async def create_event(self, payload: CalendarEventCreate) -> CalendarEvent:
        ...
    async def update_event(self, event_id: str, payload: CalendarEventUpdate) -> CalendarEvent:
        ...
    async def delete_event(self, event_id: str) -> CalendarDeleteResult:
        ...
```

If real integrations are not ready, implement mock/stub backends with clear contracts. Do not hardcode credentials.

## Required Tools

Implement these logical tools:

### Web

```text
web_search
Risk: SAFE_READ_ONLY
```

### Gmail

```text
gmail_search_messages → SENSITIVE_READ
gmail_read_message → SENSITIVE_READ
gmail_send_email → EXTERNAL_WRITE
```

### Calendar

```text
calendar_search_events → SENSITIVE_READ
calendar_create_event → EXTERNAL_WRITE
calendar_update_event → EXTERNAL_WRITE
calendar_delete_event → DESTRUCTIVE
```

## Risk Policy

Use deterministic classification first.

Do **not** require LLM-based risk classification in V1.

Risk levels:

```python
class ToolRiskLevel(str, Enum):
    SAFE_READ_ONLY = "safe_read_only"
    SENSITIVE_READ = "sensitive_read"
    EXTERNAL_WRITE = "external_write"
    DESTRUCTIVE = "destructive"
    UNKNOWN = "unknown"
```

Default behavior:

* `SAFE_READ_ONLY`: approval not required
* `SENSITIVE_READ`: approval not required by default, but configurable
* `EXTERNAL_WRITE`: approval required
* `DESTRUCTIVE`: approval required
* `UNKNOWN`: approval required

Configuration:

```python
class AgentConfig(BaseSettings):
    agent_enabled: bool = True
    require_approval_for_sensitive_read: bool = False
    require_approval_for_external_write: bool = True
    require_approval_for_destructive: bool = True
    require_approval_for_unknown: bool = True
    enable_llm_risk_classifier: bool = False
```

Document clearly:

```text
SENSITIVE_READ operations may expose private user data.
Set require_approval_for_sensitive_read=True if stricter privacy control is desired.
```

LLM-assisted risk classification may be added later, but must be disabled by default.

## Final Answer Grounding

If tools were executed, the final answer must be grounded on tool results.

The agent must not fabricate:

* Web search results
* Emails
* Calendar events
* Tool outputs

Final answer generation must receive tool results as explicit context.

If a tool fails, returns empty results, or is rejected by the user, the final answer must clearly say so.

## API Server Integration

Update the existing `/v1/chat/completions` flow.

Add config flag:

```text
ENABLE_AGENT_ORCHESTRATION=true
```

Behavior:

* If enabled:

  * route calls `AgentService.achat(...)`
* If disabled:

  * route preserves existing behavior and calls `LLMService.achat(...)`

Do not break:

* `/health`
* `/v1/models`
* existing non-agent chat behavior
* Open WebUI compatibility
* existing OpenAI-style error envelope

## Streaming Behavior

Be explicit and deterministic.

For V1, agent orchestration does not need to support streaming.

When:

```json
"stream": true
```

and agent orchestration is enabled, choose one deterministic behavior:

Preferred:

```text
Return a clear unsupported_feature error: agent streaming is not supported yet.
```

Do not fake token streaming.

Do not silently buffer and pretend it is streaming.

Existing direct LLM streaming should remain unchanged when agent orchestration is disabled.

## Error Handling

Create typed exceptions:

```python
class AgentError(Exception): ...
class PlanningError(AgentError): ...
class ToolExecutionError(AgentError): ...
class ToolNotFoundError(AgentError): ...
class ToolValidationError(AgentError): ...
class ApprovalRequiredError(AgentError): ...
class ApprovalNotFoundError(AgentError): ...
class CheckpointNotFoundError(AgentError): ...
```

Map these errors into existing OpenAI-style error envelopes in `api_server`.

## Testing Requirements

Write unit tests under:

```text
tests/unit/agent_orchestration/
```

Required tests:

1. Agent can answer without tools.
2. Planner can produce a valid tool call.
3. Planner output with hallucinated tool name is rejected.
4. Planner output with invalid arguments is rejected.
5. Safe read-only tool executes without approval.
6. Sensitive read does not require approval by default.
7. Sensitive read requires approval when configured.
8. Risky tool returns approval request instead of executing.
9. Risky tool must not execute before approval.
10. Approval reply resumes execution.
11. Rejection reply skips execution.
12. Unknown tool raises `ToolNotFoundError`.
13. Tool execution failure raises `ToolExecutionError`.
14. Gmail send email requires approval.
15. Calendar delete event requires approval.
16. Web search does not require approval by default.
17. API server routes to `AgentService` when enabled.
18. API server preserves existing `LLMService` behavior when disabled.
19. `stream=true` with agent mode returns deterministic unsupported behavior.
20. Final answer generation receives tool results as context.

Critical safety test:

```text
planner selects gmail_send_email
→ approval request returned
→ Gmail backend invocation count == 0

after APPROVE <approval_id>
→ Gmail backend invocation count == 1
```

Use mocks for:

* `LLMService`
* Tool backends
* Web search backend
* Gmail backend
* Calendar backend
* Stores

Do not require real external credentials.

## Documentation Requirements

Create:

```text
agent_orchestration/DESIGN.md
agent_orchestration/README.md
```

`DESIGN.md` must include:

* Summary of implementation
* Correct architecture diagram
* LangGraph workflow
* State model
* Planning flow
* Tool validation flow
* Tool backend design
* Risk policy
* Approval and resume flow
* Store abstractions
* API integration
* Streaming limitation
* Known limitations
* Future extension points

`README.md` must include:

* How to enable agent orchestration
* Required environment variables
* Example normal chat request
* Example tool-using request
* Example approval request
* Example approval response
* How to add a new tool
* How to configure risk approval policy

## Explicit Non-Goals for V1

Do not implement:

* Persistent memory
* Persistent session storage
* Persistent checkpoint storage
* Real multi-worker approval safety
* Agent streaming
* LLM-based risk classifier enabled by default
* RAG
* Embeddings
* Frontend-specific approval UI

## Expected Final Result

After implementation:

1. Open WebUI can still call `/v1/chat/completions`.
2. Agent orchestration can be enabled by config.
3. When enabled, user messages go through a LangGraph-based personal agent.
4. The agent can plan and use web, Gmail, and calendar tools.
5. Tool calls are strictly validated before execution.
6. Safe tools execute directly.
7. Risky tools produce approval requests and do not execute before approval.
8. User approval/rejection can be handled through normal chat messages.
9. Final answers are grounded on actual tool results.
10. Existing direct LLM behavior still works when orchestration is disabled.
11. Unit tests pass.
12. Documentation clearly explains the implementation and limitations.
