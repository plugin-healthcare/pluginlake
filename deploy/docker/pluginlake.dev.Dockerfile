# syntax=docker/dockerfile:1

# Dev Dockerfile for pluginlake (FastAPI).

FROM dhi.io/python:3.13-debian13-dev

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra fhir --no-install-project

COPY . .
RUN uv sync --frozen --extra fhir

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "pluginlake.__main__:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
