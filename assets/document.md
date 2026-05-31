# Documentation Requirements

For every core module that you create or modify, you must maintain two documentation files alongside the source code:

* `README.md`
* `DESIGN.md`

These documents are considered part of the module's deliverables and must be updated whenever the module's public behavior, architecture, or responsibilities change.

## README.md

The purpose of `README.md` is to help developers quickly understand and use the module.

It should focus on **what the module does** and **how to use it**, not on implementation details.

The README should contain:

### Purpose

A short description of the module and the problem it solves.

### Features

A concise list of supported capabilities.

### Public API

Document all public classes, functions, interfaces, and entry points exposed by the module.

### Usage Examples

Provide practical examples showing the expected way to use the module.

### Configuration

Describe any configuration options, environment variables, or dependencies required by the module.

### Extension Guide

Explain how future developers can extend the module without breaking existing behavior.

---

## DESIGN.md

The purpose of `DESIGN.md` is to help future developers and AI agents understand the module's architecture, design decisions, and current implementation state.

This document should be written assuming that a future developer has never seen the module before.

The DESIGN document must contain the following sections.

### Summary

Provide a comprehensive summary of the current implementation.

This section is extremely important.

It should describe:

* What has been implemented
* Major capabilities currently supported
* Main classes and components
* Current architecture
* Important workflows
* Known limitations
* Future extension points

A developer or AI agent should be able to read only this section and quickly understand the module's current state.

### Problem Statement

Describe the problem this module is intended to solve.

### Goals

List the architectural and functional goals.

### Non-Goals

Explicitly state what this module is not responsible for.

### Architecture Overview

Describe the high-level architecture.

Include:

* Main components
* Responsibilities of each component
* Relationships between components
* Data flow

Use diagrams when helpful.

### Design Decisions

Document important decisions made during implementation.

For each decision, explain:

* What was chosen
* Why it was chosen
* Alternatives considered
* Tradeoffs

### Public Contracts

Document important interfaces, schemas, models, protocols, and contracts that other modules depend upon.

### Extension Points

Describe where future functionality should be added.

Examples:

* New providers
* New tools
* New storage backends
* New workflows

### Current Implementation Status

Provide a checklist of implemented functionality.

Example:

* [x] Provider abstraction
* [x] Structured output support
* [x] Configuration model
* [ ] Streaming support
* [ ] Retry policies

### Testing Strategy

Describe:

* Unit testing approach
* Integration testing approach
* Critical test scenarios

### Known Limitations

Document all known constraints, shortcuts, technical debt, and incomplete features.

### Future Roadmap

List planned improvements and recommended future work.

---

## Documentation Quality Requirements

1. Documentation must reflect the actual implementation.
2. Never document features that do not exist.
3. Keep documentation synchronized with code changes.
4. Prefer clarity over completeness.
5. Assume future developers and AI agents have no prior knowledge of the module.
6. The `DESIGN.md` Summary section must always provide enough context for future work to continue without first reading the entire codebase.
7. When a major architectural decision changes, update both `README.md` and `DESIGN.md`.
8. Documentation should be treated as production code and reviewed with the same level of rigor.
