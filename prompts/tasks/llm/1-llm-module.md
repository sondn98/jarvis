# LLM Module Specification

## Purpose

Implement a centralized `llm` module that serves as the single access point for interacting with Large Language Models (LLMs) within this application.

The immediate goal is to support Ollama-hosted models using the official Ollama Python SDK. The design should allow future extension to additional providers, but this implementation must focus exclusively on Ollama.

This project is a **single AI application**, not a reusable framework or SDK. Design decisions should prioritize simplicity, maintainability, and practical usability over generality.

---

# High-Level Goals

The `llm` module should:

* Provide a simple and consistent interface for all LLM interactions.
* Hide Ollama-specific implementation details from the rest of the application.
* Support future agent-based workflows.
* Support tool calling.
* Support structured output.
* Remain stateless.
* Be easy to integrate with LangGraph in the future.
* Be easy to test.

The `llm` module should not become a framework or orchestration layer.

---

# Architectural Principles

## Keep It Simple

Favor:

* Simplicity over abstraction
* Readability over flexibility
* Maintainability over extensibility
* Explicitness over cleverness

Avoid introducing architecture that does not solve a current problem.

Do not add:

* Plugin systems
* Middleware systems
* Registry systems
* Event buses
* Dependency injection frameworks
* Capability discovery systems
* Provider orchestration layers
* Generic framework-style abstractions

When requirements are ambiguous:

1. Do not introduce additional features.
2. Do not expand the scope.
3. Choose the simplest implementation that satisfies the stated requirements.
4. Document assumptions where necessary.
5. Prefer maintainability over flexibility.

---

## Stateless Design

The `llm` module must remain stateless.

The module is responsible for:

* Sending requests to an LLM provider
* Receiving responses
* Translating provider-specific responses into internal models
* Validating structured outputs
* Parsing tool-call responses

The module must NOT manage:

* Conversation history
* Session state
* Memory
* Agent state
* Context windows
* RAG retrieval
* Tool execution
* Workflow orchestration

These concerns belong to higher-level layers.

---

# Repository Structure

The implementation should use the following structure:

```text
.
├── llm/
│   ├── __init__.py
│   ├── config.py
│   ├── exceptions.py
│   ├── models.py
│   ├── service.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py
│       └── ollama.py
│
├── tests/
│   ├── unit/
│   │   └── llm/
│   │       ├── test_config.py
│   │       ├── test_models.py
│   │       ├── test_service.py
│   │       └── providers/
│   │           └── test_ollama.py
│   │
│   ├── integration/
│   ├── fixtures/
│   └── conftest.py
│
└── pyproject.toml
```

Notes:

* Tests must not be placed inside the `llm` package.
* The project uses a centralized test structure.
* The implementation should be compatible with `pytest`.
* The project uses `uv` for dependency management.

---

# Configuration

## Requirements

Configuration must be centralized.

Configuration should be loaded from environment variables and/or application configuration.

At minimum support:

* Ollama base URL
* Default model
* Request timeout
* Default generation parameters

Example configuration fields:

```python
OLLAMA_BASE_URL
DEFAULT_MODEL
REQUEST_TIMEOUT
DEFAULT_TEMPERATURE
DEFAULT_TOP_P
DEFAULT_MAX_TOKENS
```

## Validation

Configuration should be validated during startup.

Invalid configuration should fail fast with meaningful exceptions.

Examples:

* Missing model
* Invalid timeout
* Invalid URL
* Invalid generation parameters

---

# Internal Models

Use **Pydantic** for all public models.

Avoid loosely typed dictionaries in public APIs.

Provider-specific payloads must never leave provider implementations.

---

## Message Model

Use a single message model.

Example:

```python
Message(
    role=MessageRole.USER,
    content="Hello"
)
```

### Message Roles

At minimum support:

```python
SYSTEM
USER
ASSISTANT
TOOL
```

Use an enum for roles.

### Purpose

The message model becomes the canonical message format used throughout the application.

Providers are responsible for translating this model into provider-specific formats.

---

## Tool Definition Model

Use OpenAI-style tool schemas.

Example:

```python
ToolDefinition(
    name="search_docs",
    description="Search internal documentation",
    parameters={
        ...
    }
)
```

### Requirements

A tool definition should contain:

* Name
* Description
* Parameter schema

The model should be serializable and provider-agnostic.

Tool definitions must NOT contain executable Python functions.

Tool execution belongs to higher layers.

---

## Tool Call Model

Represent model-requested tool calls as strongly typed objects.

Example:

```python
ToolCall(
    id="...",
    name="search_docs",
    arguments={...}
)
```

This object should be returned to the caller when the model requests tool execution.

---

## Structured Output Support

Structured output is an expected future use case and should be supported from Day 1.

Example:

```python
response = await llm.achat(
    messages=messages,
    response_model=TaskPlan,
)
```

Where:

```python
class TaskPlan(BaseModel):
    ...
```

### Validation

When a response model is provided:

1. The model generates structured output.
2. The response is parsed.
3. Pydantic validates the result.

If validation fails:

* Raise a dedicated exception.
* Do not silently repair the response.
* Do not attempt retries.

Fail fast.

---

## Response Model

All public APIs should return typed response objects.

Example:

```python
ChatResponse(
    content="...",
    tool_calls=[],
    finish_reason="stop"
)
```

### Purpose

The response format should remain stable regardless of whether:

* Text was generated
* Tool calls were generated
* Structured output was generated

Do not expose raw Ollama responses.

---

# Public API

The module should provide a simple interface.

Examples:

```python
llm.generate(prompt)

llm.chat(messages)

llm.chat(
    messages=messages,
    tools=tools
)

await llm.achat(...)

await llm.agenerate(...)
```

### Requirements

Public APIs should:

* Accept internal message models
* Accept optional tool definitions
* Accept optional response models
* Return typed responses

Public APIs should not expose provider-specific concepts.

---

# Async Support

Async support is required.

The implementation should provide:

```python
chat()
achat()

generate()
agenerate()
```

### Reasoning

The project is expected to adopt LangGraph in the future.

LangGraph and multi-agent workflows benefit significantly from asynchronous execution.

Async support should be implemented now rather than retrofitted later.

---

# Tool Calling

Tool calling is a first-class requirement.

---

## Responsibilities of the LLM Module

The module should:

* Accept tool definitions
* Send tool definitions to Ollama
* Detect tool-call responses
* Parse tool-call responses
* Return structured tool-call objects

---

## Responsibilities of Higher Layers

Higher layers should:

* Execute tools
* Manage tool registries
* Handle tool security
* Route tool results back to the LLM

The LLM module must never execute tools.

---

## Expected Flow

1. Caller sends messages and tool definitions.
2. Model requests a tool call.
3. LLM module returns structured tool-call objects.
4. Agent executes tools.
5. Agent sends tool results back.
6. LLM generates final response.

---

# Provider Layer

Only Ollama should be implemented.

However, provider-specific code should remain isolated.

---

## Provider Interface

Create a minimal provider abstraction.

Do not over-engineer.

The abstraction exists solely to avoid coupling the application to Ollama-specific implementation details.

---

## Ollama Provider

Use the official Ollama Python SDK.

The provider implementation should:

* Translate internal message models
* Translate tool definitions
* Handle Ollama-specific responses
* Convert responses into internal models
* Raise internal exceptions

The provider should not expose SDK-specific objects.

---

# Error Handling

Define meaningful custom exceptions.

Examples:

```python
LLMError
ConfigurationError
ProviderError
TimeoutError
StructuredOutputError
ToolCallParsingError
```

The exact hierarchy may vary.

---

## Required Error Scenarios

Handle:

* Ollama unavailable
* Connection failure
* Timeout
* Invalid provider response
* Invalid configuration
* Unsupported model
* Structured output validation failure
* Tool-call parsing failure

Avoid generic exceptions whenever possible.

---

# Logging

Use standard Python logging.

---

## INFO Level

Log:

* Request start
* Request completion

Avoid logging full prompts by default.

---

## DEBUG Level

May include:

* Request metadata
* Response metadata
* Timing information

Avoid sensitive payloads unless explicitly useful.

---

## ERROR Level

Log:

* Provider failures
* Validation failures
* Unexpected exceptions

Include enough information for debugging.

---

# Retry Behavior

Do not implement retries.

If a request fails:

* Raise an exception
* Let callers decide retry behavior

Future retry support may be added later.

---

# Streaming

Do not implement streaming.

The design should allow streaming support in the future.

Do not spend implementation effort on streaming support during this task.

---

# LangGraph Compatibility

The implementation should be easy to integrate into LangGraph nodes.

Requirements:

* Stateless design
* Async APIs
* Typed models
* Clear request/response boundaries

Do not implement LangGraph-specific code.

Simply ensure the API design works naturally within future LangGraph workflows.

---

# Unit Testing

Write unit tests.

The goal is confidence, not coverage metrics.

---

## Test Location

Place tests under:

```text
tests/unit/llm/
```

Do not place tests inside the implementation package.

---

## Test Philosophy

Focus on:

* Core functionality
* Failure handling
* Important edge cases

Avoid:

* Chasing 100% coverage
* Testing trivial code
* Large amounts of repetitive test code

---

## Required Test Cases

### Configuration

Test:

* Successful configuration loading
* Missing required configuration
* Invalid configuration values

---

### Models

Test:

* Message validation
* Tool definition validation
* Structured output validation

---

### Service Layer

Test:

* Successful chat completion
* Successful generation
* Structured output flow
* Tool-calling flow

---

### Provider Layer

Test:

* Ollama response parsing
* Tool-call parsing
* Invalid provider responses
* Timeout handling
* Provider failures

---

## Edge Cases

At minimum cover:

* Ollama unavailable
* Timeout
* Invalid response structure
* Malformed tool call
* Missing configuration
* Structured output validation failure

Use mocks and fixtures where appropriate.

Unit tests should remain:

* Fast
* Deterministic
* Isolated

---

# Documentation

Provide:

* Docstrings for public APIs
* Brief architecture summary
* Usage examples

Keep documentation concise and practical.

Avoid generating large design documents.

---

# Non-Goals

The following are explicitly out of scope for this implementation:

* Streaming support
* Embedding generation
* Memory management
* Conversation persistence
* RAG integration
* Agent orchestration
* Retry mechanisms
* Multi-provider support
* Usage/token accounting
* Observability frameworks
* MCP support
* LangChain integration
* LangGraph integration

The implementation should be designed so these features can be added later, but they must not be implemented as part of this task.

---

# Deliverables

Provide:

1. Brief architecture summary (maximum 10 bullets)
2. Directory structure
3. Configuration implementation
4. Pydantic models
5. Exceptions
6. Provider abstraction
7. Ollama provider implementation
8. Service layer
9. Async APIs
10. Tool-calling support
11. Structured output support
12. Usage examples
13. Unit tests
14. Brief explanation of major design decisions

After presenting the architecture summary, proceed directly to implementation.
