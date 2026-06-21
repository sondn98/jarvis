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
| `MCP_CONFIG_PATH` | _(unset)_ | Path to the MCP servers JSON config. When unset, the agent has no tools. See [Configuring MCP Tools](#configuring-mcp-tools). |
| `REQUIRE_APPROVAL_FOR_SENSITIVE_READ` | `false` | Require approval before sensitive-read operations |
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

## Example: Tool-Using Request

Tools come from configured MCP servers (see [Configuring MCP Tools](#configuring-mcp-tools)).
A tool whose configured risk is `SAFE_READ_ONLY` executes without approval:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "messages": [{"role": "user", "content": "Search for the latest AI news"}]
  }'
```

The agent plans the matching MCP tool (e.g. `<server>.search`), executes it, and
returns a grounded answer.

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
      "content": "I need your approval before doing this:\n\nTool: gmail.send_email\nArguments:\n{\n  \"to\": \"alice@example.com\",\n  \"subject\": \"Meeting tomorrow\",\n  \"body\": \"The meeting is tomorrow.\"\n}\n\nRisk: Tool 'gmail.send_email' has risk level: external_write\n\nReply with:\nAPPROVE a3f1c2d4e5\nor\nREJECT a3f1c2d4e5"
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

## Configuring MCP Tools

Tools are supplied by external [MCP](https://modelcontextprotocol.io) servers over
Streamable HTTP — Jarvis connects to them as an MCP client. Point `MCP_CONFIG_PATH`
at a JSON file shaped like Claude Desktop's `mcpServers` block:

```json
{
  "mcpServers": {
    "gmail": {
      "url": "https://mcp.example.com/gmail/mcp",
      "headers": {"Authorization": "Bearer ${GMAIL_MCP_TOKEN}"},
      "default_risk_level": "external_write",
      "tool_risk_levels": {"search_messages": "sensitive_read"}
    }
  }
}
```

Per server:

- `url` (required) — the server's Streamable HTTP endpoint.
- `headers` (optional) — sent on every request; `${VAR}` is expanded from the
  process environment, so secrets stay in `.env` rather than in the JSON file.
- `default_risk_level` (optional, default `unknown`) — risk applied to every tool
  from this server (drives the approval policy above).
- `tool_risk_levels` (optional) — per-tool risk overrides, keyed by the tool's
  (un-namespaced) MCP name.
- `timeout` (optional, default `30`) — per-request connect/call timeout in seconds.

The config file is parsed at startup; servers are contacted **lazily on the first
agent request** (cached for the process lifetime). Each tool is registered under the
namespaced name `<server>.<tool>` to avoid collisions. A server that is unreachable
is skipped with a warning so it cannot take down the agent. No graph changes are
needed — the planner automatically includes discovered tools in its prompt.

Quick connectivity check against a server:

```bash
MCP_TEST_URL="https://your-server/mcp" MCP_TEST_AUTH="Bearer <token>" \
    uv run python scripts/manual_mcp_check.py
```

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
