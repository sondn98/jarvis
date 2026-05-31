# API Server Module Implementation Task

## Overview

You are a senior AI software engineer.

Before doing any implementation, read `prompts/prompt.md` to understand how you should work in this project.

Also read the existing `llm` module specification and implementation before planning the `api_server` module.

The `api_server` module must use the `llm` module as its only mechanism for interacting with backend LLM providers. It must never call Ollama directly.

---

# Project Context

This project is a single personal AI application, not a reusable framework.

The repository uses `uv` for dependency management.

An existing `llm` module has already been designed and implemented.

The `llm` module:

* Is stateless
* Handles all LLM communication
* Uses the Ollama Python SDK internally
* Supports typed request/response models
* Supports tool calling
* Supports structured output validation
* Exposes sync and async APIs
* Does not manage memory
* Does not manage RAG
* Does not manage orchestration
* Does not execute tools

The new `api_server` module should sit directly above the `llm` module.

Architecture:

```text
Open WebUI
    ↓
OpenAI-Compatible API
    ↓
api_server
    ↓
llm
    ↓
Ollama
```

---

# Primary Goal

Implement an OpenAI-compatible API server that Open WebUI can connect to.

The API server should:

* Expose HTTP endpoints
* Accept OpenAI-style requests
* Translate requests into internal `llm` requests
* Invoke the `llm` module
* Translate internal responses into OpenAI-compatible responses

The API server should not contain business logic related to LLM execution.

---

# Module Responsibilities

The `api_server` module owns:

```text
- FastAPI application setup
- HTTP routes
- OpenAI-compatible request schemas
- OpenAI-compatible response schemas
- request validation
- response validation
- adapter layer
- HTTP error handling
- API server configuration
- logging
```

The `api_server` module must not own:

```text
- Ollama SDK interaction
- memory
- conversation persistence
- RAG
- orchestration
- tool execution
- embeddings
- retries
- LangGraph integration
- LangChain integration
- streaming implementation
- user management
```

---

# Required Technology

Use:

```text
FastAPI
Pydantic
Python logging
pytest
```

Prefer async route handlers.

---

# Required Endpoints

## GET /health

Purpose:

Health check endpoint.

Example response:

```json
{
  "status": "ok"
}
```

Requirements:

* No LLM calls
* No Ollama calls

---

## GET /v1/models

Purpose:

Allow Open WebUI to discover available models.

Return an OpenAI-compatible response.

Example:

```json
{
  "object": "list",
  "data": [
    {
      "id": "model-name",
      "object": "model",
      "created": 0,
      "owned_by": "local"
    }
  ]
}
```

Important:

Do not call Ollama directly.

If model listing is not already exposed by the `llm` module, create a planning question before implementation.

---

## POST /v1/chat/completions

Purpose:

Main endpoint used by Open WebUI.

Initial request fields to support:

```text
model
messages
temperature
top_p
max_tokens
tools
tool_choice
response_format
stream
```

Example response:

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1710000000,
  "model": "model-name",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello"
      },
      "finish_reason": "stop"
    }
  ]
}
```

---

# Streaming

Do not implement streaming.

If:

```json
{
  "stream": true
}
```

Return an OpenAI-compatible error.

Example:

```json
{
  "error": {
    "message": "Streaming is not supported yet.",
    "type": "unsupported_feature"
  }
}
```

The design must allow streaming to be added later.

---

# Tool Calling

Tool calling is a first-class requirement.

The API server should:

* Accept OpenAI-style tools
* Accept OpenAI-style tool_choice
* Pass tools into the `llm` module

The API server must not:

* Execute tools

If tool calls are returned by the `llm` module, convert them into OpenAI-compatible tool call responses.

---

# Structured Output

The existing `llm` module supports structured output validation.

Support OpenAI-style `response_format` only if it can be mapped clearly to the internal implementation.

If mapping behavior is unclear:

Create a planning question.

Do not invent behavior.

---

# Adapter Layer

Create explicit adapters.

Do not place translation logic inside route handlers.

Route flow:

```text
Request
    ↓
Validate
    ↓
OpenAI → LLM Adapter
    ↓
LLM Call
    ↓
LLM → OpenAI Adapter
    ↓
Response
```

Adapters should handle:

```text
- Message conversion
- Role conversion
- Tool schema conversion
- Tool call conversion
- Generation parameter conversion
- Finish reason conversion
```

---

# Configuration

Create configuration support for:

```text
host
port
default_model
api_key
enable_api_key_auth
log_level
```

Do not assume authentication is required.

If unclear, ask.

---

# Error Handling

Use consistent OpenAI-style errors.

Example:

```json
{
  "error": {
    "message": "Human readable message",
    "type": "error_type",
    "param": null,
    "code": null
  }
}
```

Suggested mappings:

```text
Validation Error       -> 400 / 422
Unsupported Feature    -> 400
Authentication Failure -> 401
LLM Failure            -> 500 / 502
```

Never expose stack traces to clients.

---

# Logging

Use standard Python logging.

INFO:

```text
Server startup
Request received
Request completed
```

DEBUG:

```text
Request metadata
Model selection
Generation settings
Adapter details
```

ERROR:

```text
LLM failures
Unexpected failures
```

Do not log prompt contents by default.

---

# Suggested Folder Structure

```text
api_server/
├── __init__.py
├── app.py
├── config.py
├── dependencies.py
├── errors.py
├── logging.py
│
├── routes/
│   ├── __init__.py
│   ├── health.py
│   ├── models.py
│   └── chat.py
│
├── schemas/
│   ├── __init__.py
│   ├── openai.py
│   └── errors.py
│
├── adapters/
│   ├── __init__.py
│   ├── openai_to_llm.py
│   └── llm_to_openai.py
```

---

# Application Entrypoint

The project must expose a single top-level entrypoint.

Update the root-level:

```text
main.py
```

to become the official application entrypoint.

Purpose:

```text
- Open WebUI integration
- Future agents
- Automation tools
- Tests
- Deployment systems
```

should all use the same entrypoint.

---

## Entrypoint Responsibilities

The root-level `main.py` should:

```text
- initialize configuration
- initialize logging
- create the FastAPI application
- expose the FastAPI app object
- start the API server when executed directly
```

Expected pattern:

```python
app = create_app()

if __name__ == "__main__":
    ...
```

Use an application factory exposed by the API server module.

Example:

```python
from api_server import create_app

app = create_app()
```

---

## Dependency Direction

Required:

```text
main.py
    ↓
api_server
    ↓
llm
    ↓
ollama
```

Forbidden:

```text
llm
    ↓
api_server
```

---

## Stable Import Surface

Future modules should be able to use:

```python
from main import app
```

without importing route implementations.

---

# Testing Requirements

Tests are mandatory.

A task is not complete until tests pass.

Do not postpone testing until the end.

Every public component must be tested during implementation.

---

## API Server Unit Tests

Create tests for:

```text
OpenAI → LLM mapping
LLM → OpenAI mapping
Role conversion
Tool schema conversion
Tool call conversion
Health endpoint
Model endpoint
Chat completion endpoint
Stream rejection
Error mapping
```

Suggested location:

```text
tests/unit/api_server/
```

---

## Entrypoint Unit Tests

Create tests for:

```text
Application factory creation
FastAPI app exposure
Importing main.py does not start server
Configuration initialization
Logging initialization
Route registration
```

Suggested location:

```text
tests/unit/main/
    test_main.py
```

or repository equivalent.

---

## Integration-Style Tests

Verify:

```text
main.py
    ↓
api_server
```

integration.

At minimum:

```text
FastAPI app exists
Routes are registered
Health endpoint works
OpenAI-compatible endpoints exist
```

Use:

```python
fastapi.testclient.TestClient
```

Mock the `llm` module where appropriate.

Do not require a running Ollama server.

---

# Planning Process

Before implementation:

Create:

```text
prompts/tmp/plan.md
```

The plan must:

* Use checkboxes
* Break work into steps
* Include questions when clarification is required

Question format:

```text
[Question] Question goes here.

[Answer]
```

Do not make critical architectural decisions without confirmation.

After creating the plan:

STOP.

Request review and approval.

Only after approval may implementation begin.

Update the plan continuously as work progresses.

---

# Clarifications To Verify Before Implementation

If not already obvious from the repository, ask:

```text
1. Should Open WebUI use authentication?
2. Where should model listing come from?
3. What APIs does the llm module expose?
4. How should response_format be mapped?
5. Should unknown OpenAI fields be ignored or rejected?
6. What default model should be used?
7. Should future OpenAI endpoints be planned now?
8. Is main.py intended to be only an API entrypoint or the bootstrap entrypoint for the entire future AI platform?
9. Does an existing application entrypoint already exist?
10. Are there existing uv scripts that should be reused?
```

---

# Non-Goals

Do not implement:

```text
Streaming
RAG
Memory
Conversation persistence
Tool execution
LangGraph integration
LangChain integration
Embeddings
Retries
Distributed tracing
Metrics frameworks
User management
Multi-provider routing
MCP
```

---

# Final Deliverable

Produce a clean, tested, documented `api_server` module that:

```text
Open WebUI
    ↓
OpenAI-Compatible API
    ↓
api_server
    ↓
llm
    ↓
Ollama
```

The implementation should be minimal, strongly typed, easy to extend, and aligned with the project's existing `llm` architecture.
