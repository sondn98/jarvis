# jarvis

My personal AI Agent

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
