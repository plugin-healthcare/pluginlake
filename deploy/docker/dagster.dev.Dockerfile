# syntax=docker/dockerfile:1

# Dev Dockerfile for dagster (runs `dagster dev` — all-in-one).

FROM dhi.io/python:3.13-debian13-dev

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --extra infra --extra fhir --no-install-project

COPY . .
RUN uv sync --frozen --extra infra --extra fhir

ENV PATH="/app/.venv/bin:$PATH" \
    DAGSTER_HOME="/app/config/dagster" \
    DAGSTER_MODULE="pluginlake.definitions"

EXPOSE 3000

CMD dagster dev -h 0.0.0.0 -p 3000 -m "$DAGSTER_MODULE"
