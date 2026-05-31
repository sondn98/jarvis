# llm

Centralized access point for interacting with Large Language Models (LLMs) within this application. All LLM calls go through this module; no other module should import provider SDKs directly.

---

## Features

- Simple, consistent interface for chat and generation
- Sync and async APIs (`chat` / `achat`, `generate` / `agenerate`)
- Tool calling — pass tool definitions, receive structured `ToolCall` objects
- Structured output — pass a Pydantic model, receive a validated instance serialized as JSON
- Provider-agnostic internal models (`Message`, `ToolDefinition`, `ToolCall`, `ChatResponse`)
- Configuration loaded from environment variables with validation at startup
- Meaningful custom exceptions; no silent failures

---

## Public API

### `LLMService`

The primary entry point.

```python
from llm import LLMConfig, LLMService

config = LLMConfig()          # reads from environment
llm = LLMService(config)
```

| Method | Description |
|---|---|
| `chat(messages, *, tools, response_model, **kwargs)` | Send a list of messages; return `ChatResponse` |
| `achat(...)` | Async variant of `chat` |
| `generate(prompt, **kwargs)` | Wrap a single string in a user message and call `chat` |
| `agenerate(prompt, **kwargs)` | Async variant of `generate` |

All methods accept optional keyword overrides (`model`, `temperature`, `top_p`, `max_tokens`).

### Models

| Class | Purpose |
|---|---|
| `Message` | Single message with `role` (`MessageRole`) and `content` |
| `MessageRole` | Enum: `SYSTEM`, `USER`, `ASSISTANT`, `TOOL` |
| `ToolDefinition` | OpenAI-style tool schema (`name`, `description`, `parameters`) |
| `ToolCall` | Model-requested tool invocation (`id`, `name`, `arguments`) |
| `ChatResponse` | Unified response (`content`, `tool_calls`, `finish_reason`) |

### Exceptions

| Exception | Raised when |
|---|---|
| `LLMError` | Base for all module errors |
| `ConfigurationError` | Config is missing or invalid |
| `ProviderError` | Provider is unavailable or returns an error |
| `TimeoutError` | Request exceeds `REQUEST_TIMEOUT` |
| `StructuredOutputError` | Structured output fails Pydantic validation |
| `ToolCallParsingError` | Tool-call response cannot be parsed |

---

## Usage Examples

### Simple generation

```python
from llm import LLMConfig, LLMService

llm = LLMService(LLMConfig())
response = llm.generate("Explain recursion in one sentence.")
print(response.content)
```

### Chat with system prompt

```python
from llm import LLMConfig, LLMService, Message, MessageRole

llm = LLMService(LLMConfig())
messages = [
    Message(role=MessageRole.SYSTEM, content="You are a concise assistant."),
    Message(role=MessageRole.USER, content="What is the capital of France?"),
]
response = llm.chat(messages)
print(response.content)
```

### Tool calling

```python
from llm import LLMConfig, LLMService, Message, MessageRole, ToolDefinition

llm = LLMService(LLMConfig())

search_tool = ToolDefinition(
    name="search_docs",
    description="Search internal documentation",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)

messages = [Message(role=MessageRole.USER, content="Find docs about authentication.")]
response = llm.chat(messages, tools=[search_tool])

if response.tool_calls:
    for tc in response.tool_calls:
        print(tc.name, tc.arguments)   # execute the tool yourself, then send results back
```

### Structured output

```python
from pydantic import BaseModel
from llm import LLMConfig, LLMService, Message, MessageRole

class TaskPlan(BaseModel):
    steps: list[str]
    estimated_minutes: int

llm = LLMService(LLMConfig())
messages = [Message(role=MessageRole.USER, content="Plan a 3-step deployment.")]
response = await llm.achat(messages, response_model=TaskPlan)

plan = TaskPlan.model_validate_json(response.content)
print(plan.steps)
```

---

## Configuration

All configuration is read from environment variables (or a `.env` file in the project root).

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_MODEL` | *(required)* | Model name passed to Ollama (e.g. `llama3.2`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `REQUEST_TIMEOUT` | `60.0` | Per-request timeout in seconds |
| `DEFAULT_TEMPERATURE` | `0.7` | Sampling temperature (0.0 – 2.0) |
| `DEFAULT_TOP_P` | `0.9` | Top-p nucleus sampling (0.0 – 1.0) |
| `DEFAULT_MAX_TOKENS` | `2048` | Maximum tokens to generate |

`DEFAULT_MODEL` is the only required variable. All others have safe defaults.

Invalid values raise `ConfigurationError` immediately at construction time.

---

## Extension Guide

### Adding a new provider

1. Create `llm/providers/<name>.py` implementing `BaseProvider` (`chat` and `achat`).
2. Pass an instance of your provider to `LLMService(config, provider=MyProvider(config))`.
3. No changes to the service layer, models, or exceptions are needed.

### Adding a new model or field

Internal models (`Message`, `ChatResponse`, etc.) are Pydantic models. Add optional fields with defaults to remain backward compatible with existing callers.

### Per-request overrides

Pass keyword arguments to `chat` / `generate` to override defaults for a single call:

```python
llm.generate("Hello", model="mistral", temperature=0.2, max_tokens=512)
```
