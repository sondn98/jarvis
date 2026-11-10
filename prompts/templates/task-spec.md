# <Task Title>

<!--
Template for `prompts/tasks/<N>-<slug>.md` — a feature / module build spec.
House style observed in archive tasks 1-6 and 8: prose spec, prescriptive,
heavy on explicit non-goals. Drop sections that don't apply; don't invent
content to fill them.
-->

## Purpose

What is being built and why, in 2-5 sentences. State what layer of Jarvis it
belongs to and what problem it solves today — not hypothetically.

Note whether this is a single application concern or something intended to be
reusable. (Jarvis is a single AI application, not a framework or SDK: prefer
simplicity, maintainability, and practical usability over generality.)

---

# High-Level Goals

* <Goal>
* <Goal>

What this component should explicitly **not** become (e.g. "should not become an
orchestration layer").

---

# Architectural Principles

Favor:

* Simplicity over abstraction
* Readability over flexibility
* Maintainability over extensibility
* Explicitness over cleverness

Do not add (unless the task explicitly asks for it):

* Plugin systems, middleware, registries, event buses
* Dependency injection frameworks
* Generic framework-style abstractions

When requirements are ambiguous: do not expand scope, choose the simplest
implementation that satisfies the stated requirements, and document assumptions.

---

# Repository Structure

```text
<module>/
├── __init__.py
├── config.py
└── ...

tests/
└── unit/
    └── <module>/
        └── ...
```

Notes:

* Tests live under `tests/`, never inside the implementation package.
* `uv` for dependency management, `pytest` for tests.

---

# Configuration

Which settings this needs, how they're loaded (`pydantic-settings` `BaseSettings`
reading env vars + project-root `.env`, per existing convention), and what must
fail fast at startup.

---

# <Functional Requirements>

One section per area of behaviour. Be concrete — show the intended call shapes,
model shapes, and log lines rather than describing them abstractly.

```python
# illustrative, not binding
```

---

# Error Handling

Named exceptions this introduces, and the failure scenarios that must be
handled. Avoid generic exceptions in public APIs.

---

# Logging

What is logged at INFO / DEBUG / TRACE. No sensitive content at INFO. Lazy
logging (`logger.debug("x: %s", x)`), not f-strings.

---

# Unit Testing

Where tests go (`tests/unit/<module>/`), and the required cases — core
functionality, failure handling, important edge cases. The goal is confidence,
not a coverage number. Avoid testing trivial code.

---

# Documentation

What to write or update (`<module>/DESIGN.md`, `<module>/README.md`,
root `README.md`). Keep it concise; no large design documents.

---

# Non-Goals

Explicitly out of scope for this task:

* <Non-goal>
* <Non-goal>

The implementation should be designed so these can be added later, but they must
not be implemented as part of this task.

---

# Deliverables

1. <Deliverable>
2. <Deliverable>
