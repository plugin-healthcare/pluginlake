# syntax=docker/dockerfile:1

# Dockerfile for pluginlake (FastAPI + dagster code-server).
# Both services use the same image with different commands.

# --- Build stage ---
FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

# DuckDB extensions are installed at build time, so the read-only container never downloads them at runtime.
RUN mkdir -p /opt/duckdb && HOME=/opt/duckdb /app/.venv/bin/python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL ducklake'); c.execute('INSTALL postgres')"

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder --chmod=755 /opt/duckdb /opt/duckdb

# The container runs as the host user and HOME holds the installed DuckDB extensions.
ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/opt/duckdb
