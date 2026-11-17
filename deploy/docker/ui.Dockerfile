# syntax=docker/dockerfile:1

# Dockerfile for the pluginlake Streamlit datastation dashboard.

FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --only-group dashboard

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/pluginlake-ui/datastation/ /app/
COPY assets/ /app/assets/
COPY .streamlit/ /app/.streamlit/

# The container runs as the host user, so HOME must be writable: Streamlit stores a machine id there and fails to send the theme without it.
ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"]

CMD ["streamlit", "run", "app.py"]
