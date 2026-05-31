# GitHub CI/CD Workflow Implementation

Before starting any implementation, read the project's guidance documents, prompts, architecture documents, README files, DESIGN documents, and existing codebase structure. Follow all project conventions and instructions already established.

---

# Context

This project is a personal AI platform.

Current architecture:

```text
main.py
   │
   ▼
api_server
   │
   ▼
llm
   │
   ▼
Ollama
```

The project uses:

* Python
* FastAPI
* uv
* Pydantic
* Docker containerization
* GitHub as source control

The application entrypoint is:

```python
from main import app
```

The project is intended to evolve into a larger AI platform containing future modules such as:

* Memory
* RAG
* Agents
* Automation
* Scheduling

The CI/CD implementation should provide a clean production-grade foundation while remaining simple and maintainable.

---

# Objective

Create a GitHub Actions CI/CD workflow that validates code quality, security, test correctness, and container build integrity.

The workflow should be suitable for a production-oriented Python backend service while avoiding unnecessary complexity.

---

# Planning Requirement

Before modifying any files:

Create:

```text
prompts/tmp/plan.md
```

The plan must include:

* Implementation steps with checkboxes
* Assumptions
* Risks
* Questions requiring clarification
* Proposed workflow architecture

Use:

```text
[Question]
...

[Answer]

```

for any unresolved item.

Do not start implementation until the plan is complete and ready for review.

---

# Required Deliverables

Create or update:

```text
.github/workflows/ci.yml
```

If required:

```text
Dockerfile
.dockerignore
README.md
DESIGN.md
```

Only modify documentation when necessary to explain the workflow.

---

# CI/CD Design Requirements

The workflow should run on:

```yaml
on:
  pull_request:
    branches:
      - main

  push:
    branches:
      - main
```

The workflow should use GitHub-hosted runners.

Use official GitHub Actions whenever possible.

Preferred actions include:

* actions/checkout
* actions/setup-python
* docker/setup-buildx-action
* docker/login-action
* docker/build-push-action
* actions/cache

Do not introduce unnecessary third-party GitHub Actions.

---

# Python Version

The workflow must automatically read and use the version defined in:

```text
.python-version
```

Do not hardcode the Python version unless the project does not provide one.

---

# Dependency Management

The project uses:

```text
uv
```

Use uv consistently throughout the workflow.

Examples:

```bash
uv sync
uv run pytest
uv run ruff check .
```

Avoid pip unless absolutely necessary.

---

# Workflow Structure

The workflow should be organized into logical jobs.

Example structure:

```text
lint
security
test
build
publish
```

The workflow should fail fast.

Expensive jobs such as image publishing should only run after all validation jobs pass.

---

# Linting and Formatting

Use Ruff.

Required checks:

```bash
uv run ruff check .
uv run ruff format --check .
```

Linting failures should fail the workflow.

---

# Type Checking

Inspect the repository.

If a type checker is already configured:

* mypy
* pyright

then execute it.

If no type checker exists:

* do not introduce one automatically
* document the decision

Do not create unnecessary work for the project.

---

# Unit Testing

Run all tests from:

```text
tests/
```

Use pytest.

Example:

```bash
uv run pytest
```

Requirements:

* Tests must run without Ollama
* Tests must run without Open WebUI
* Tests must run without external services
* Mock LLM dependencies where appropriate

Test failures must fail the workflow.

---

# Security Scanning

Implement lightweight but meaningful security validation.

Required:

## Dependency Vulnerability Scan

Use:

```text
pip-audit
```

Run dependency vulnerability checks as part of CI.

The scan should fail the workflow on critical dependency vulnerabilities.

## Dependency Review

For pull requests, use GitHub Dependency Review if appropriate.

Do not require external paid services.

---

# Caching

Implement caching to improve CI speed.

Cache:

## Python Dependencies

Use GitHub Actions cache support for:

* uv downloads
* dependency resolution artifacts

## Docker Layers

Use Buildx cache support.

The goal is to avoid rebuilding unchanged layers.

---

# Container Build

The workflow must verify that the application container builds successfully.

Container builds must run for:

* Pull Requests
* Pushes to main

This validates Dockerfile correctness before merge.

---

# Dockerfile Requirements

If a Dockerfile does not exist:

Create one.

Requirements:

## Build Strategy

Use:

```text
Multi-stage build
```

where appropriate.

## Dependency Installation

Use:

```text
uv
```

inside the build process.

## Image Optimization

Minimize image size.

Avoid shipping:

* tests
* prompts
* documentation
* local tooling artifacts
* caches

## Runtime User

Run the application as a non-root user if practical.

## Entrypoint

Use the project's root-level entrypoint:

```python
main.py
```

Do not guess runtime commands.

If startup behavior is unclear:

create a question and wait for clarification.

---

# Docker Image Publishing

Publish images to Docker Hub.

Repository:

```text
sondn1/jarvis
```

Use:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
```

from GitHub Secrets.

Do not hardcode credentials.

Do not use Docker Hub passwords.

---

# Image Tagging Strategy

Publish immutable and mutable tags.

Required:

```text
sondn1/jarvis:sha-<git-sha>
sondn1/jarvis:latest
```

Examples:

```text
sondn1/jarvis:sha-a1b2c3d
sondn1/jarvis:latest
```

---

# Publishing Rules

## Pull Requests

Allowed:

```text
Lint
Security Scan
Unit Test
Docker Build Validation
```

Not allowed:

```text
Docker Push
```

## Pushes to Main

Allowed:

```text
Lint
Security Scan
Unit Test
Docker Build
Docker Push
```

Only publish after all previous jobs pass.

---

# Secrets Handling

Docker Hub credentials must be sourced from GitHub Secrets.

Expected secrets:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
```

The workflow must not print credentials.

The workflow should fail gracefully if publishing is enabled but required secrets are unavailable.

---

# Permissions

Use least-privilege permissions.

Example:

```yaml
permissions:
  contents: read
```

Grant additional permissions only where required.

Do not use overly permissive settings.

---

# Documentation Updates

Update documentation to include:

## CI Overview

Explain:

* When workflows run
* What checks are performed
* Merge expectations

## Docker Publishing

Explain:

* Image repository
* Tag strategy
* Publishing flow

## Secrets Setup

Document how to configure:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
```

in:

```text
GitHub
→ Repository Settings
→ Secrets and Variables
→ Actions
```

## Local Validation

Document how developers can run the same checks locally.

Examples:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
docker build .
```

---

# Verification Requirements

After implementation:

Run or validate every command used in CI where practical.

Examples:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
docker build .
```

If any command cannot be validated, document the reason.

---

# Future Compatibility

The workflow and Dockerfile should remain compatible with future deployment through:

* Kubernetes
* ArgoCD
* FluxCD
* GitOps workflows

Do not couple the implementation to a specific deployment platform.

---

# Important Constraints

Do not:

* Require a running Ollama instance
* Require Open WebUI
* Depend on external infrastructure
* Depend on local developer state
* Push images from pull requests
* Hardcode secrets
* Make critical architectural assumptions

When uncertain, stop and ask for clarification.

The final result should be a clean, maintainable, production-oriented CI/CD foundation suitable for a growing AI platform.
