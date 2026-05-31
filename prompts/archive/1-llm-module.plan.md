# LLM Module – Implementation Plan

## Architecture Summary

1. `llm/config.py` — Pydantic-based config loaded from environment variables; validated at startup
2. `llm/exceptions.py` — Custom exception hierarchy; no generic exceptions in public APIs
3. `llm/models.py` — Pydantic models for `Message`, `ToolDefinition`, `ToolCall`, `ChatResponse`; provider-agnostic
4. `llm/providers/base.py` — Minimal abstract interface (`chat`, `achat`); prevents coupling to Ollama
5. `llm/providers/ollama.py` — Concrete Ollama SDK adapter; translates internal models ↔ Ollama types
6. `llm/service.py` — `LLMService`; thin orchestration layer exposing `chat`, `achat`, `generate`, `agenerate`
7. `llm/__init__.py` — Re-exports public symbols (`LLMService`, models, exceptions)
8. Tests under `tests/unit/llm/`; mocked provider; fast, deterministic, isolated

---

## Directory Structure

```text
llm/
├── __init__.py
├── config.py
├── exceptions.py
├── models.py
├── service.py
└── providers/
    ├── __init__.py
    ├── base.py
    └── ollama.py

tests/
├── conftest.py
├── fixtures/
├── integration/
└── unit/
    └── llm/
        ├── test_config.py
        ├── test_models.py
        ├── test_service.py
        └── providers/
            └── test_ollama.py
```

---

## Implementation Steps

- [x] **Step 1 – Dependencies**: Add `ollama` and `pydantic-settings` to `pyproject.toml` via `uv add`
- [x] **Step 2 – Exceptions**: Implement `llm/exceptions.py` with the full exception hierarchy
- [x] **Step 3 – Models**: Implement `llm/models.py` (`MessageRole`, `Message`, `ToolDefinition`, `ToolCall`, `ChatResponse`)
- [x] **Step 4 – Config**: Implement `llm/config.py` using `pydantic-settings` to load from env vars; validate on instantiation
- [x] **Step 5 – Provider base**: Implement `llm/providers/base.py` with abstract `chat` / `achat` methods
- [x] **Step 6 – Ollama provider**: Implement `llm/providers/ollama.py`; translate models, call SDK, handle errors, support tool calling and structured output
- [x] **Step 7 – Service layer**: Implement `llm/service.py` (`LLMService`) with `chat`, `achat`, `generate`, `agenerate`
- [x] **Step 8 – Public API**: Update `llm/__init__.py` to re-export public symbols
- [x] **Step 9 – Test scaffolding**: Create `tests/` directory structure and `conftest.py`
- [x] **Step 10 – Config tests**: Write `tests/unit/llm/test_config.py`
- [x] **Step 11 – Model tests**: Write `tests/unit/llm/test_models.py`
- [x] **Step 12 – Service tests**: Write `tests/unit/llm/test_service.py`
- [x] **Step 13 – Provider tests**: Write `tests/unit/llm/providers/test_ollama.py`

---

## Questions

### [Question 1]
The spec requires a `tests/` directory, but the project already contains a `test/` directory (with an `__init__.py`). Should I:

- **Option A** – Create the new `tests/` structure as specified, leaving the existing `test/` untouched.
- **Option B** – Use the existing `test/` directory and adapt the spec's structure to match (i.e. `test/unit/llm/…`).

This affects folder structure and is a critical decision.

## [Answer 1] Rename `test/` to `tests/` and use it as test folder

---

### [Question 2]
The spec says configuration should be loaded from "environment variables and/or application configuration". I plan to use `pydantic-settings` (a thin Pydantic extension) which handles env var loading automatically with full validation. The alternative is plain `os.environ` lookups inside a regular Pydantic `BaseModel`.

- **Option A** – Use `pydantic-settings` (`BaseSettings`): cleaner env var mapping, `.env` file support, no extra boilerplate. Requires adding `pydantic-settings` as a dependency.
- **Option B** – Use plain `os.environ` inside a regular Pydantic `BaseModel`: zero new dependencies, slightly more manual.

This affects dependencies and is a critical decision.

## [Answer 2] Use `pydantic-settings`

