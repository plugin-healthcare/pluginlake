# syntax=docker/dockerfile:1

# Dockerfile for pluginlake (FastAPI + dagster code-server).
# Both services use the same image with different commands.

# --- Build stage ---
FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"
