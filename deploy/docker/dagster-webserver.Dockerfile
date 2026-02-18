# syntax=docker/dockerfile:1

# Dockerfile for dagster-webserver and dagster-daemon.
# Does not include source code — connects to code-server via gRPC.

# --- Build stage ---
FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group dagster-infra --no-install-project

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    DAGSTER_HOME="/app/config/dagster"

COPY config/dagster/ /app/config/dagster/

EXPOSE 3000
