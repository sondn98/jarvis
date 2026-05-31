# CI/CD Implementation Plan

## Assumptions

1. Python version `3.13` is defined in `.python-version` and will be read dynamically in CI via `cat .python-version`.
2. Application entrypoint is `python main.py` — `APIServerConfig` defaults to host `0.0.0.0`, port `8000`, which is Docker-compatible without additional env overrides.
3. No type checker (mypy/pyright) is configured in this repository. Per the task requirement ("do not introduce one automatically"), none will be added. Documented below.
4. `DEFAULT_MODEL` env var is already handled in `tests/conftest.py` via `os.environ.setdefault`, so no extra CI env var is needed.
5. `ruff` and `pip-audit` are not currently in dev dependencies and must be added.
6. `uv` will be bootstrapped in CI via `pip install uv` (one-time bootstrap; uv is then used for all subsequent Python operations to satisfy the "avoid pip" constraint).
7. The `publish` job will fail gracefully if Docker Hub secrets are missing — `docker/login-action` produces a clear auth error and the job fails with an actionable message.
8. Docker layer caching will use `actions/cache` with the Buildx `type=gha` cache backend.

## No Type Checker Decision

No mypy or pyright is configured in this repository. The task requirement explicitly states: "If no type checker exists: do not introduce one automatically." This decision is preserved here for future reference if the team decides to add type checking later.

## Proposed Workflow Architecture

```
Trigger: pull_request → main
         push → main
         push → tag v*

Jobs:

  lint     (ruff check + format) ─────────────┐
  security (pip-audit + dep-review on PRs) ───┤──► publish  (tag v* push only)
  test     (pytest) ──────────────────────────┤    needs: [lint, security, test, build]
  build    (docker build, no push) ───────────┘
```

Publishing rules:
- **Pull Requests**: lint, security, test, build — no Docker push
- **Push to main**: lint, security, test, build — no Docker push (validation only)
- **Push of `v*` tag**: lint, security, test, build, then publish (build + push to Docker Hub)

## Image Tagging Strategy

- `sondn1/jarvis:<git-tag>` — immutable version tag derived directly from the Git tag (e.g., `v1.2.3`)
- `sondn1/jarvis:latest` — mutable, updated on every successful release tag push

## Deliverables

| File | Action |
|------|--------|
| `pyproject.toml` | Add `ruff`, `pip-audit` to `[dependency-groups] dev` |
| `uv.lock` | Updated via `uv sync` |
| `Dockerfile` | New — multi-stage, uv install, non-root user, port 8000 |
| `.dockerignore` | New — exclude tests, prompts, docs, caches, .venv |
| `.github/workflows/ci.yml` | New — 5-job workflow |
| `README.md` | Update — add CI/CD section |

## Implementation Steps

- [x] **Step 1** — Add `ruff` and `pip-audit` to dev dependencies in `pyproject.toml`; run `uv sync` to update `uv.lock`
- [x] **Step 2** — Create `Dockerfile` with multi-stage build: `builder` stage installs deps via uv; `runtime` stage copies app, runs as non-root user, exposes port 8000, `CMD ["python", "main.py"]`
- [x] **Step 3** — Create `.dockerignore` to exclude: `.venv`, `tests/`, `prompts/`, `assets/`, `*.md`, `.git`, `__pycache__`, `.pytest_cache`
- [x] **Step 4** — Create `.github/workflows/ci.yml` with:
  - Triggers: `pull_request → master`, `push → master`, `push → tags v*`
  - `lint` job: `uv run ruff check .` + `uv run ruff format --check .`
  - `security` job: `uv run pip-audit` + `actions/dependency-review-action` (PRs only)
  - `test` job: `uv run pytest`
  - `build` job: docker buildx build, `push: false`, validates Dockerfile correctness — runs for PRs, pushes to main, and tag pushes
  - `publish` job: docker buildx build + push with tags `sondn1/jarvis:<git-tag>` and `sondn1/jarvis:latest`, `if: startsWith(github.ref, 'refs/tags/v')`, `needs: [lint, security, test, build]`
- [x] **Step 5** — Update `README.md` with CI overview, Docker publishing info, secrets setup instructions, local validation commands, and a "Creating a Release" section (e.g., `git tag v1.0.0 && git push origin v1.0.0`)
- [x] **Step 6** — Validate locally: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`, `docker build .`
  - `ruff check`: PASS
  - `ruff format --check`: PASS
  - `pytest`: PASS (132 passed)
  - `docker build`: PASS — image built successfully (`jarvis:local`)
  - `docker run` smoke test: PASS — `/health` returns `{"status":"ok"}` (requires `DEFAULT_MODEL` env var at runtime, e.g. `-e DEFAULT_MODEL=llama3.2`)

## Risks

1. **pip-audit may flag existing CVEs** — `langchain` and its transitive dependencies are known to accumulate CVEs. If pip-audit blocks CI immediately, individual CVEs can be suppressed with `--ignore-vuln <VULN-ID>` after review. This is an expected first-run risk.
2. **Ruff not yet configured** — `pyproject.toml` has no `[tool.ruff]` section. Ruff will run with defaults, which may flag existing code. A minimal `[tool.ruff]` config will be added to `pyproject.toml` if needed.
3. **Docker Python 3.13 base image** — `python:3.13-slim` is stable and available. No risk.
4. **`pytest-asyncio` mode** — tests use `pytest-asyncio`; if `asyncio_mode` is not configured, warnings may appear. Will check and configure `asyncio_mode = "auto"` in `[tool.pytest.ini_options]` if needed.
