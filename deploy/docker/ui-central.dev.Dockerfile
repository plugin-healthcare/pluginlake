# syntax=docker/dockerfile:1

# Dev Dockerfile for pluginlake central dashboard (Streamlit).

FROM dhi.io/python:3.13-debian13-dev

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --only-group dashboard

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8502

CMD ["streamlit", "run", "src/pluginlake-ui/central/app.py", "--server.port=8502", "--server.address=0.0.0.0", "--server.headless=true", "--server.runOnSave=true", "--server.useStarlette=true"]
