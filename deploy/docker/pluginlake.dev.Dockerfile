# syntax=docker/dockerfile:1

# Dev Dockerfile for pluginlake (FastAPI).
# Installs fhir + infra extras for both API and code-server usage.
# Command is specified in docker-compose.dev.yaml.

FROM dhi.io/python:3.13-debian13-dev

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra fhir --extra infra --no-install-project

COPY . .
RUN uv sync --frozen --extra fhir --extra infra

ENV PATH="/app/.venv/bin:$PATH" \
    DAGSTER_HOME="/app/config/dagster"
