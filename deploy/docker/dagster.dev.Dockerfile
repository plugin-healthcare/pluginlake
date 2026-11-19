# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e

# Dev Dockerfile for dagster (runs `dagster dev` — all-in-one).

FROM dhi.io/python:3.13-debian13-dev@sha256:cc070c5f483069c53e251a63d114f1f17af806f257a67c9106967247d3ee092a

COPY --from=dhi.io/uv:0-debian13-dev@sha256:e0f9b9c9bf4b95ddd229886777961a28ebbfd38fb00d96f2ae58eb2b843b1de6 /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --extra infra --no-install-project

COPY . .
RUN uv sync --frozen --extra infra

ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv" \
    DAGSTER_HOME="/app/config/dagster" \
    DAGSTER_MODULE="pluginlake.definitions"

RUN cp deploy/docker/entrypoint.sh /usr/local/bin/pluginlake-entrypoint.sh \
    && chmod +x /usr/local/bin/pluginlake-entrypoint.sh

EXPOSE 3000

ENTRYPOINT ["/usr/local/bin/pluginlake-entrypoint.sh"]
# dagster_env sets DAGSTER_PG_PASSWORD from the secret and creates the Dagster database if missing.
CMD python -m pluginlake.deploy.dagster_env --ensure-db dagster dev -h 0.0.0.0 -p 3000 -m "$DAGSTER_MODULE"
