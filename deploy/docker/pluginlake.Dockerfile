# syntax=docker/dockerfile:1

# Dockerfile for pluginlake (FastAPI + dagster code-server + run worker).
# Used by: pluginlake API, dagster-code-server, and run worker containers.

# --- Build stage ---
FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --extra fhir --extra infra

COPY src/ src/
RUN uv sync --frozen --no-dev --extra fhir --extra infra

RUN mkdir -p /app/.data

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder --chown=nonroot:nonroot /app/.data /app/.data
COPY config/dagster/dagster.yaml /app/config/dagster/dagster.yaml

ENV PATH="/app/.venv/bin:$PATH" \
    DAGSTER_HOME="/app/config/dagster"
