# Task: Add Debug Logging for LLM Responses and Agent Orchestration

## Objective

The current architecture introduces an orchestration layer between the API and the LLM.

While this improves separation of concerns, it makes debugging significantly harder because:

* Multiple LLM calls may occur during a single user request.
* Planning decisions are hidden inside LangGraph.
* Tool selection and tool outputs are not easily visible.
* Final responses may be generated from multiple intermediate steps.

Implement comprehensive debug logging that allows developers to inspect LLM interactions and orchestration behavior when running the system in development or troubleshooting environments.

## Requirements

### Logging Visibility Rules

Logging must respect configured log levels.

#### INFO and Above

No prompt or response content should be logged.

Only operational metadata should be logged:

```text
Received chat request
Selected provider
Selected model
Tool execution started
Tool execution completed
Request completed
```

#### DEBUG

At DEBUG level, log:

* LLM request messages
* Structured planner outputs
* Tool selection decisions
* Tool arguments
* Tool results
* Final LLM responses
* Approval requests
* Approval decisions

Example:

```text
[DEBUG] Planner response:
{
  "requires_tool": true,
  "tool_name": "web_search"
}
```

```text
[DEBUG] Tool result:
{
  "result_count": 5
}
```

```text
[DEBUG] Final response:
"Based on the search results..."
```

#### TRACE

Implement a TRACE-level capability.

If the existing logging framework does not support TRACE, add a custom level.

TRACE should include:

* Full message history sent to the LLM
* Raw provider responses
* Full LangGraph state transitions
* State before node execution
* State after node execution
* Checkpoint contents
* Approval checkpoint state
* Tool execution payloads
* Tool execution outputs
* Final generated response

Example:

```text
[TRACE] State before planner:
{...}
```

```text
[TRACE] Raw LLM response:
{...}
```

## Logging Design

### Centralized Logger

Do not use ad-hoc print statements.

Use the project's standard logging infrastructure.

Create a dedicated logger hierarchy:

```python
jarvis.agent
jarvis.agent.graph
jarvis.agent.planner
jarvis.agent.tools
jarvis.agent.approval
jarvis.llm
```

### Lazy Logging

Avoid expensive string construction when DEBUG/TRACE is disabled.

Use:

```python
logger.debug("Planner output: %s", plan)
```

not:

```python
logger.debug(f"Planner output: {plan}")
```

### Structured Logging

Prefer structured payloads.

Example:

```python
logger.debug(
    "Tool selected",
    extra={
        "tool": tool_name,
        "risk_level": risk_level,
    },
)
```

Do not rely solely on free-form strings.

## LLM Module Logging

Update the `llm` module.

### DEBUG

Log:

```text
Provider
Model
Messages
Tools supplied
Structured output schema
Response content
Tool calls returned
Finish reason
```

### TRACE

Additionally log:

```text
Raw provider request
Raw provider response
Streaming chunks
Provider metadata
Token usage metadata (if available)
```

### Streaming

For streaming responses:

DEBUG:

```text
Stream started
Stream completed
Chunk count
Duration
```

TRACE:

```text
Every chunk
```

## Agent Planner Logging

### DEBUG

Log:

```text
User request
Planner decision
Selected tool
Generated plan
```

### TRACE

Log:

```text
Planner prompt
Planner messages
Raw LLM output
Validation results
```

## Tool Logging

### DEBUG

Log:

```text
Tool selected
Tool arguments
Tool result summary
Execution duration
```

### TRACE

Log:

```text
Full request payload
Full tool response
```

## Approval Logging

### DEBUG

Log:

```text
Approval requested
Approval id
Tool name
Risk level
User approved
User rejected
```

### TRACE

Log:

```text
Checkpoint state
Pending tool call
Stored graph state
Resumed graph state
```

## Sensitive Data Protection

Implement configurable redaction.

Configuration:

```python
class LoggingConfig(BaseSettings):
    redact_sensitive_data: bool = True
```

### Redaction Targets

At minimum:

```text
Email addresses
Email bodies
Calendar descriptions
OAuth tokens
API keys
Passwords
Authorization headers
Cookies
```

Example:

```text
alice@example.com
```

becomes

```text
a***@example.com
```

### Default Behavior

Redaction must be enabled by default.

Developers may disable it explicitly for local debugging.

## LangGraph Node Instrumentation

Add logging around every node execution.

Example:

```text
Node started: planner
Node completed: planner
Duration: 120ms
```

TRACE:

```text
State before
State after
State diff
```

## Unit Tests

Add tests covering:

1. DEBUG logs emitted for planner responses.
2. DEBUG logs emitted for final LLM responses.
3. TRACE logs emitted for raw provider responses.
4. Sensitive fields are redacted by default.
5. Redaction can be disabled.
6. Tool execution logs appear.
7. Approval logs appear.
8. Streaming logs work correctly.
9. INFO level does not emit response content.
10. TRACE logs contain state transition information.

Use pytest `caplog` for validation.

## Documentation

Update:

* `llm/DESIGN.md`
* `agent_orchestration/DESIGN.md`
* `README.md`

Document:

* Logger hierarchy
* DEBUG behavior
* TRACE behavior
* Redaction behavior
* Example log outputs

## Constraints

* No print statements.
* No logging of sensitive content at INFO level.
* Logging must be disabled automatically when DEBUG/TRACE are not enabled.
* Use lazy logging patterns.
* Redaction enabled by default.
* Do not significantly impact runtime performance when DEBUG/TRACE are disabled.

## Expected Outcome

When running with:

```bash
LOG_LEVEL=DEBUG
```

developers can see:

* planner decisions
* tool usage
* LLM responses
* approval workflow

When running with:

```bash
LOG_LEVEL=TRACE
```

developers can inspect:

* raw LLM interactions
* graph transitions
* checkpoint state
* full orchestration execution path

without modifying application code.
