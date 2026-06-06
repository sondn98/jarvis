# agent_orchestration

LangGraph-based personal AI agent module for Jarvis.

---

## How to Enable Agent Orchestration

Set the environment variable:

```bash
ENABLE_AGENT_ORCHESTRATION=true
```

Or add it to your `.env` file. The existing `/v1/chat/completions` endpoint automatically routes through the agent when enabled.

---

## Required Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ENABLE_AGENT_ORCHESTRATION` | `false` | Enable agent mode on the chat endpoint |
| `REQUIRE_APPROVAL_FOR_SENSITIVE_READ` | `false` | Require approval before Gmail/Calendar read operations |
| `REQUIRE_APPROVAL_FOR_EXTERNAL_WRITE` | `true` | Require approval before sending emails / creating events |
| `REQUIRE_APPROVAL_FOR_DESTRUCTIVE` | `true` | Require approval before deleting events |
| `REQUIRE_APPROVAL_FOR_UNKNOWN` | `true` | Require approval for tools with unknown risk |
| `ENABLE_LLM_RISK_CLASSIFIER` | `false` | Enable LLM-assisted risk classification (no effect in V1) |

---

## Example: Normal Chat Request

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "messages": [{"role": "user", "content": "What is the capital of France?"}]
  }'
```

```json
{
  "choices": [{
    "message": {"role": "assistant", "content": "The capital of France is Paris."},
    "finish_reason": "stop"
  }]
}
```

---

## Example: Tool-Using Request (Web Search)

Web search is `SAFE_READ_ONLY` and executes without approval:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "messages": [{"role": "user", "content": "Search for the latest AI news"}]
  }'
```

The agent plans `web_search`, executes it, and returns a grounded answer.

---

## Example: Approval Request (Send Email)

Email sending is `EXTERNAL_WRITE` and requires approval:

**Request:**
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "messages": [{"role": "user", "content": "Send an email to alice@example.com saying the meeting is tomorrow"}]
  }'
```

**Response:**
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "I need your approval before doing this:\n\nTool: gmail_send_email\nArguments:\n{\n  \"to\": \"alice@example.com\",\n  \"subject\": \"Meeting tomorrow\",\n  \"body\": \"The meeting is tomorrow.\"\n}\n\nRisk: Tool 'gmail_send_email' has risk level: external_write\n\nReply with:\nAPPROVE a3f1c2d4e5\nor\nREJECT a3f1c2d4e5"
    }
  }]
}
```

---

## Example: Approval Response

Send the approval ID (copy it exactly from the message):

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "messages": [
      {"role": "user", "content": "Send an email to alice@example.com saying the meeting is tomorrow"},
      {"role": "assistant", "content": "<approval message from above>"},
      {"role": "user", "content": "APPROVE a3f1c2d4e5"}
    ],
    "conversation_id": "same-id-as-before"
  }'
```

The agent resumes from the saved checkpoint, sends the email, and returns the final answer.

To reject: reply with `REJECT a3f1c2d4e5`.

---

## How to Add a New Tool

1. Create your args schema:

```python
from pydantic import BaseModel

class _MyArgs(BaseModel):
    query: str
```

2. Implement `BaseTool`:

```python
from agent_orchestration.tools.base import BaseTool
from agent_orchestration.tools.risk import ToolRiskLevel
from agent_orchestration.models import ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful."
    risk_level = ToolRiskLevel.SAFE_READ_ONLY
    args_schema = _MyArgs

    async def arun(self, arguments: dict) -> ToolResult:
        # call your backend
        output = "result"
        return ToolResult(tool_name=self.name, arguments=arguments, output=output, success=True)
```

3. Register it in `api_server/app.py` inside `_build_agent_service()`:

```python
registry.register(MyTool(my_backend))
```

No graph changes needed. The planner automatically includes the new tool in its prompt.

---

## How to Configure Risk Approval Policy

Control which risk levels require approval via environment variables:

```bash
# Require approval before any Gmail/Calendar read
REQUIRE_APPROVAL_FOR_SENSITIVE_READ=true

# Allow email sends without approval (not recommended)
REQUIRE_APPROVAL_FOR_EXTERNAL_WRITE=false

# Keep destructive actions gated (default)
REQUIRE_APPROVAL_FOR_DESTRUCTIVE=true
```

Or pass `AgentConfig` directly when building `AgentService` in tests:

```python
config = AgentConfig(require_approval_for_sensitive_read=True)
```

---

## Streaming

Agent mode does not support `"stream": true`. The server returns `400 unsupported_feature`. Set `stream=false` (or omit it) when using agent mode.

Direct LLM streaming (with `ENABLE_AGENT_ORCHESTRATION=false`) is unaffected.
