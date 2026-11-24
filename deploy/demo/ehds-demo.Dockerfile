# syntax=docker/dockerfile:1

# Demo image: the pluginlake image with the pluginlake-ehds-demo project installed.
# Build context is the pluginlake checkout; the named context "ehds" is the pluginlake-ehds-demo checkout.

# --- Build stage ---
FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/
# The ehds-demo project has git dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable

# --no-sources ignores the project's local editable path to pluginlake and keeps the one installed above.
# The named context "wheels" may hold local wheels and an overrides.txt that replaces unreachable pins.
COPY --from=ehds pyproject.toml uv.lock README.md /ehds/
COPY --from=ehds src/ /ehds/src/
COPY --from=wheels / /wheels/
RUN uv pip install --python /app/.venv/bin/python --no-sources \
    $(if [ -f /wheels/overrides.txt ]; then echo --override /wheels/overrides.txt; fi) /ehds

RUN mkdir -p /opt/duckdb && HOME=/opt/duckdb /app/.venv/bin/python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL ducklake'); c.execute('INSTALL postgres')"

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder --chmod=755 /opt/duckdb /opt/duckdb

ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/opt/duckdb
