# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e

# Image `dagster-webserver`: dagster-webserver and dagster-daemon.
# Definitions are loaded from the code server via gRPC, so pluginlake is not installed:
# only the Dagster packages (dependency group `dagster-webserver`) and the standalone
# dagster_env launcher. Runs as the non-root user 65532 on a read-only root filesystem.

# --- Build stage ---
FROM dhi.io/python:3.13-debian13-dev@sha256:cc070c5f483069c53e251a63d114f1f17af806f257a67c9106967247d3ee092a AS builder

COPY --from=dhi.io/uv:0-debian13-dev@sha256:e0f9b9c9bf4b95ddd229886777961a28ebbfd38fb00d96f2ae58eb2b843b1de6 /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --only-group dagster-webserver

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13@sha256:953d20534e4db354421e84f2b83967031b0b224202c719ffbe7485851e9cef60

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/pluginlake/deploy/dagster_env.py /app/dagster_env.py

ENV PATH="/app/.venv/bin:$PATH" \
    DAGSTER_HOME="/app/config/dagster" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY config/dagster/workspace.yaml /app/config/dagster/
COPY config/dagster/dagster.production.yaml /app/config/dagster/dagster.yaml

USER 65532:65532

# Sets DAGSTER_PG_PASSWORD (read by dagster.yaml) from the Docker secret, then runs the compose command.
ENTRYPOINT ["python", "/app/dagster_env.py"]

EXPOSE 3000
