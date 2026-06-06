Here's a comprehensive version that combines the LLM streaming work and the API server integration work into a single implementation task.

# Task: Implement End-to-End Streaming Support Across LLM and API Server

You are tasked with implementing end-to-end streaming support for the project.

The current system supports only non-streaming responses, which prevents chat clients from receiving tokens incrementally as they are generated.

The objective of this task is to introduce a clean, production-quality streaming architecture that works from the LLM provider all the way to the API layer while preserving backward compatibility with all existing non-streaming behavior.

The implementation should be designed not only for Ollama, but also for future providers and future OpenAI-compatible integrations.

---

# Objectives

The final architecture should support the following flow:

```text
Client
    ↓
api_server
    ↓
llm abstraction
    ↓
provider implementation
    ↓
Ollama
```

For non-streaming requests:

```text
Client
    ↓
api_server
    ↓
llm.chat(...)
    ↓
Ollama
    ↓
Full Response
```

For streaming requests:

```text
Client
    ↓
api_server
    ↓
llm.stream_chat(...)
    ↓
Ollama Stream
    ↓
Incremental Chunks
    ↓
Client
```

The implementation must remain provider-agnostic and future-proof.

---

# Functional Requirements

## 1. Preserve Existing Behavior

Do not break any existing public APIs.

All current non-streaming functionality must continue to work exactly as before.

Existing callers should not need modification.

Streaming must be additive.

Default behavior must remain non-streaming.

---

## 2. Introduce Streaming into the LLM Abstraction

Review the current LLM module architecture and extend it with a provider-agnostic streaming interface.

Recommended shape:

```python
async for chunk in llm.stream_chat(request):
    ...
```

or a project-consistent equivalent.

Requirements:

* expose a generic streaming interface
* hide provider-specific details
* support future providers
* be easy for API handlers to consume
* avoid exposing Ollama response structures outside provider code

The design should clearly indicate that future providers are expected to implement both:

```python
chat(...)
stream_chat(...)
```

or equivalent methods.

---

## 3. Create a Stream Chunk Model

Introduce a normalized project-level streaming response model.

If the project already uses Pydantic, use Pydantic.

Recommended fields:

```python
content: str
done: bool

provider: str | None
model: str | None

finish_reason: str | None

raw: dict | None
```

The model should represent a provider-independent chunk of generated content.

Callers should never need to understand Ollama-specific payload structures.

---

## 4. Implement Ollama Streaming

Implement streaming support in the Ollama provider.

Requirements:

* enable Ollama streaming mode
* consume streamed responses incrementally
* convert provider chunks into the project stream model
* yield chunks immediately
* preserve useful metadata
* emit completion information when available
* avoid buffering the full response

The implementation should be memory efficient and suitable for long responses.

---

## 5. Provider Response Normalization

Provider-specific parsing must remain inside provider code.

Upper layers should only consume project-level abstractions.

Bad example:

```python
chunk["message"]["content"]
```

outside provider code.

Good example:

```python
chunk.content
```

outside provider code.

The rest of the application should not know how Ollama structures its responses.

---

## 6. Streaming Error Handling

Handle:

* Ollama unavailable
* connection failures
* model not found
* malformed provider chunks
* unexpected provider exceptions
* interrupted streams
* client cancellation

Errors must be surfaced clearly.

Do not silently swallow failures.

Reuse existing exception patterns where possible.

Introduce additional exceptions only if genuinely necessary.

Examples:

```python
LLMError
LLMProviderError
LLMStreamingError
LLMStreamingNotSupportedError
```

Do not over-engineer the exception hierarchy.

---

## 7. Streaming Cancellation

Ensure resources are handled correctly when the caller stops consuming a stream.

Example:

```python
async for chunk in llm.stream_chat(request):
    if stop_requested:
        break
```

The implementation should not leave dangling resources where avoidable.

Document any cleanup assumptions imposed by the Ollama SDK.

---

# API Server Integration

## 8. Make the API Server Streaming-Aware

The API server must be updated so that it understands streaming requests.

Review existing request and response models.

Add a streaming-aware request design.

Example:

```python
stream: bool = False
```

or an equivalent design that fits the existing API contract.

The API layer should decide whether to call:

```python
llm.chat(...)
```

or

```python
llm.stream_chat(...)
```

based on the request.

---

## 9. Implement End-to-End Streaming Flow

Update the API layer so streamed chunks can flow from the provider all the way to the client.

Required path:

```text
HTTP Client
    ↓
api_server
    ↓
llm.stream_chat(...)
    ↓
Ollama
```

The API server should not buffer the full response before returning it.

Streaming responses should be forwarded incrementally.

Implement the simplest robust approach supported by the current framework.

---

## 10. Keep Responsibilities Separated

Maintain clear architectural boundaries.

API server responsibilities:

```text
- request validation
- request routing
- response serialization
- streaming transport
- protocol handling
```

LLM module responsibilities:

```text
- provider abstraction
- provider selection
- Ollama integration
- stream generation
- response normalization
```

Do not place HTTP concerns inside the LLM module.

Do not place provider-specific logic inside the API layer.

---

## 11. Open WebUI Compatibility

The design must be suitable for future Open WebUI integration.

The goal is not necessarily to implement Open WebUI compatibility today.

However, avoid architectural choices that would make future integration difficult.

The implementation should move the project toward:

```text
Open WebUI
      ↓
OpenAI-compatible API
      ↓
api_server
      ↓
llm
      ↓
Ollama
```

Requirements:

* keep stream chunks provider-agnostic
* keep API responses decoupled from Ollama
* keep transport separated from generation
* make OpenAI-compatible endpoints straightforward to add later

Document any design decisions that support this goal.

---

## 12. Future Compatibility Considerations

Design with future providers in mind.

Potential future providers:

* OpenAI
* Anthropic
* Gemini
* OpenRouter
* Local vLLM deployments
* Local llama.cpp deployments

The streaming abstraction should not require redesign when a new provider is added.

---

# Documentation Updates

Update relevant documentation.

At minimum:

## README

Document:

* non-streaming usage
* streaming usage
* request examples
* API examples
* limitations
* future roadmap

## DESIGN.md

Document:

* streaming architecture
* API flow
* provider abstraction
* chunk model
* provider normalization
* future provider onboarding requirements
* Open WebUI integration strategy

The documentation should help a future coding agent quickly understand how streaming works throughout the system.

---

# Code Quality Requirements

The implementation must:

* follow existing project structure
* use type hints
* use Pydantic where appropriate
* keep interfaces stable
* remain backward compatible
* avoid provider leakage
* avoid unnecessary dependencies
* remain simple and maintainable
* be production-oriented rather than prototype-oriented

---

# Testing Requirements

Do not create a large new streaming-specific test suite.

However:

* run all existing tests
* update existing tests if required
* add only minimal compatibility coverage if absolutely necessary
* avoid external dependencies in tests
* do not require a running Ollama instance

The goal is to preserve project quality without significantly expanding test scope.

---

# Validation

Run project validation commands before completion.

If the project uses `uv`, prefer:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

If dependency auditing is already configured:

```bash
uv run pip-audit
```

Resolve failures before marking the task complete.

---

# Deliverables

Provide:

1. Updated LLM abstraction with streaming support.
2. Updated Ollama provider implementation.
3. Normalized stream chunk model.
4. Streaming-aware API request/response contract.
5. End-to-end streaming path from API layer to Ollama.
6. Backward-compatible non-streaming behavior.
7. Documentation updates.
8. DESIGN.md updates.
9. Summary of all modified files.
10. Explanation of how future Open WebUI integration should be performed.

Before implementation, carefully analyze the existing architecture and ensure the streaming design fits naturally into the current project structure rather than forcing a completely new design.
