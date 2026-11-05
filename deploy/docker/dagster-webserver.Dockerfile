# syntax=docker/dockerfile:1

# Dockerfile for dagster-webserver and dagster-daemon.
# Definitions are loaded from the code-server via gRPC, so pluginlake is not installed:
# only the Dagster packages (dependency group `dagster-webserver`) and the standalone
# dagster_env launcher.

# --- Build stage ---
FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --only-group dagster-webserver

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/pluginlake/deploy/dagster_env.py /app/dagster_env.py

ENV PATH="/app/.venv/bin:$PATH" \
    DAGSTER_HOME="/app/config/dagster"

COPY config/dagster/workspace.yaml /app/config/dagster/
COPY config/dagster/dagster.production.yaml /app/config/dagster/dagster.yaml

# Sets DAGSTER_PG_PASSWORD (read by dagster.yaml) from the Docker secret, then runs the compose command.
ENTRYPOINT ["python", "/app/dagster_env.py"]

EXPOSE 3000
