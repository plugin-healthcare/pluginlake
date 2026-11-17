# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e

# Image `api`: FastAPI gateway and Dagster code server (same image, different command).
# Base images are pinned by digest; Dependabot (docker ecosystem) proposes updates.
# The runtime runs as the non-root user 65532 on a read-only root filesystem
# (docs/guides/security.md), so everything it needs is put in place at build time.

# --- Build stage ---
FROM dhi.io/python:3.13-debian13-dev@sha256:cc070c5f483069c53e251a63d114f1f17af806f257a67c9106967247d3ee092a AS builder

COPY --from=dhi.io/uv:0-debian13-dev@sha256:e0f9b9c9bf4b95ddd229886777961a28ebbfd38fb00d96f2ae58eb2b843b1de6 /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

# Bytecode is compiled here: the read-only runtime cannot write .pyc files.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HOME=/app

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable

# DuckDB installs extensions on first use, which needs network and a writable
# $HOME. Install them now into $HOME/.duckdb, so the runtime only loads them.
RUN /app/.venv/bin/python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL ducklake'); c.execute('INSTALL postgres')"

# Mount point of the data volume; a new named volume inherits this ownership.
RUN mkdir -p /app/.data

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13@sha256:953d20534e4db354421e84f2b83967031b0b224202c719ffbe7485851e9cef60

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/.duckdb /app/.duckdb
COPY --from=builder --chown=65532:65532 /app/.data /app/.data

ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 65532:65532

EXPOSE 8000 4000

CMD ["python", "-m", "pluginlake"]
