# syntax=docker/dockerfile:1

# Dockerfile for pluginlake datastation dashboard (Streamlit).

FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --only-group dashboard

COPY src/pluginlake-ui/datastation/ src/pluginlake-ui/datastation/
COPY assets/ assets/
COPY .streamlit/config.toml .streamlit/config.toml

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src/pluginlake-ui/datastation /app
COPY --from=builder /app/assets /app/assets
COPY --from=builder /app/.streamlit /app/.streamlit

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--server.useStarlette=true"]
