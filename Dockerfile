# ── builder ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies into /app/.venv (no-editable, no dev deps)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── runtime ───────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Copy the pre-built virtualenv from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source only
COPY main.py ./
COPY api_server ./api_server
COPY llm ./llm
COPY agent_orchestration ./agent_orchestration
COPY logging_utils ./logging_utils

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run as non-root user
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

EXPOSE 8000

CMD ["python", "main.py"]
