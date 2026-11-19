# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e

# Dev Dockerfile for pluginlake (FastAPI).

FROM dhi.io/python:3.13-debian13-dev@sha256:cc070c5f483069c53e251a63d114f1f17af806f257a67c9106967247d3ee092a

COPY --from=dhi.io/uv:0-debian13-dev@sha256:e0f9b9c9bf4b95ddd229886777961a28ebbfd38fb00d96f2ae58eb2b843b1de6 /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv"

RUN cp deploy/docker/entrypoint.sh /usr/local/bin/pluginlake-entrypoint.sh \
    && chmod +x /usr/local/bin/pluginlake-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/pluginlake-entrypoint.sh"]
CMD ["uvicorn", "pluginlake.__main__:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
