# syntax=docker/dockerfile:1

# Dockerfile for the pluginlake Streamlit dashboards.
# APP selects the dashboard (src/pluginlake-ui/<APP>), PORT its port:
#   datastation (default): --build-arg APP=datastation --build-arg PORT=8501
#   central:               --build-arg APP=central --build-arg PORT=8502

FROM dhi.io/python:3.13-debian13-dev AS builder

COPY --from=dhi.io/uv:0-debian13-dev /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --only-group dashboard

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13

ARG APP=datastation
ARG PORT=8501

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/pluginlake-ui/${APP}/ /app/
COPY assets/ /app/assets/

ENV PATH="/app/.venv/bin:$PATH" \
    STREAMLIT_SERVER_PORT=${PORT} \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

EXPOSE ${PORT}

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ['STREAMLIT_SERVER_PORT'] + '/_stcore/health')"]

CMD ["streamlit", "run", "app.py"]
