# syntax=docker/dockerfile:1

# Dev Dockerfile for pluginlake (FastAPI).

FROM dhi.io/python:3.13-debian13-dev

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "pluginlake"]
