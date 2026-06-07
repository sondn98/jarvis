# jarvis

My personal AI Agent

---

## Debug Logging

Jarvis supports three log levels with increasing verbosity. Set `LOG_LEVEL` in your `.env` or environment.

### INFO (default)

Only operational metadata is emitted — no prompt content, tool arguments, or LLM response text.

```
Received chat request
Selected provider / model
Tool execution started / completed
Request completed
```

### DEBUG

```bash
LOG_LEVEL=DEBUG
```

Logs planner decisions, tool selection, execution duration, approval workflow, and final answer metadata:

```
[DEBUG] jarvis.agent.planner  Planner invoked: user_request='Search for AI news...'
[DEBUG] jarvis.agent.planner  Planner decision: requires_tool=True, tool=web_search
[DEBUG] jarvis.agent.tools    Tool selected: web_search
[DEBUG] jarvis.agent.tools    Tool execution complete: web_search, duration: 340ms
[DEBUG] jarvis.agent.approval Approval requested: id=abc123, tool=send_email, risk_level=EXTERNAL_WRITE
[DEBUG] jarvis.agent.graph    Node completed: generate_final_answer, duration: 820ms
```

### TRACE

```bash
LOG_LEVEL=TRACE
```

Logs the full execution path including raw LLM interactions, graph state transitions, and tool payloads:

```
[TRACE] jarvis.llm            LLM full messages: [{'role': 'system', ...}, ...]
[TRACE] jarvis.llm            LLM raw response: ChatResponse(...)
[TRACE] jarvis.agent.graph    State before plan: {'conversation_id': ..., 'messages': [...]}
[TRACE] jarvis.agent.graph    State diff plan: {'plan': 'NoneType -> AgentPlan'}
[TRACE] jarvis.agent.tools    Full tool response: {'tool_name': 'web_search', 'output': '...'}
```

### Logger hierarchy

| Logger | Covers |
|---|---|
| `jarvis.llm` | Provider requests, responses, streaming chunks |
| `jarvis.agent.graph` | Node start/complete/duration, state transitions |
| `jarvis.agent.planner` | Planning decisions and LLM calls |
| `jarvis.agent.tools` | Tool selection, arguments, results |
| `jarvis.agent.approval` | Approval requests and decisions |

### Sensitive data redaction

Redaction is **enabled by default**. Emails, bearer tokens, API keys, passwords, and cookies are masked in all log output:

```
alice@example.com  →  a***@example.com
Bearer abc123      →  Bearer [REDACTED]
api_key=secret     →  api_key=[REDACTED]
```

To disable for local debugging:

```bash
REDACT_SENSITIVE_DATA=false
```

---

## CI/CD

### When workflows run

| Event | Jobs |
|---|---|
| Pull request → `master` | lint, security, test, build |
| Push to `master` | lint, security, test, build |
| Push of `v*` tag | lint, security, test, build, **publish** |

### Checks performed

- **lint** — `ruff check` (code quality) + `ruff format --check` (formatting)
- **security** — `pip-audit` (dependency vulnerability scan) + GitHub Dependency Review (PRs only)
- **test** — `pytest` (full unit test suite, no external services required)
- **build** — Docker image build validation (no push)
- **publish** — Docker image build + push to Docker Hub (release tags only)

### Merge expectations

All jobs must pass before a pull request can be merged. Publishing never occurs on branch pushes — only on versioned release tags.

---

## Docker

### Image repository

```
sondn1/jarvis
```

### Tag strategy

| Tag | When |
|---|---|
| `sondn1/jarvis:v1.2.3` | On every `v*` tag push |
| `sondn1/jarvis:latest` | Updated to newest release on every `v*` tag push |

### Creating a release

```bash
git tag v1.0.0
git push origin v1.0.0
```

This triggers the full CI pipeline. If all jobs pass, the following images are published automatically:

```
sondn1/jarvis:v1.0.0
sondn1/jarvis:latest
```

---

## Secrets setup

Configure the following secrets in **GitHub → Repository Settings → Secrets and Variables → Actions**:

| Secret | Description |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub account username |
| `DOCKERHUB_TOKEN` | Docker Hub access token (not password) |

---

## Local validation

Run the same checks locally before pushing:

```bash
# Lint
uv run ruff check .
uv run ruff format --check .

# Tests
uv run pytest

# Docker build
docker build .
```
