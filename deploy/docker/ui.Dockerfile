# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e

# Dockerfile for the pluginlake Streamlit dashboards.
# APP selects the dashboard (src/pluginlake-ui/<APP>), PORT its port:
#   datastation (default): --build-arg APP=datastation --build-arg PORT=8501
#   central:               --build-arg APP=central --build-arg PORT=8502
# Images `ui-datastation` and `ui-central`. Runs as the non-root user 65532 on a
# read-only root filesystem.

FROM dhi.io/python:3.13-debian13-dev@sha256:cc070c5f483069c53e251a63d114f1f17af806f257a67c9106967247d3ee092a AS builder

COPY --from=dhi.io/uv:0-debian13-dev@sha256:e0f9b9c9bf4b95ddd229886777961a28ebbfd38fb00d96f2ae58eb2b843b1de6 /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --only-group dashboard

# --- Runtime stage ---
FROM dhi.io/python:3.13-debian13@sha256:953d20534e4db354421e84f2b83967031b0b224202c719ffbe7485851e9cef60

ARG APP=datastation
ARG PORT=8501

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/pluginlake-ui/${APP}/ /app/
COPY assets/ /app/assets/

ENV PATH="/app/.venv/bin:$PATH" \
    STREAMLIT_SERVER_PORT=${PORT} \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

USER 65532:65532

EXPOSE ${PORT}

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ['STREAMLIT_SERVER_PORT'] + '/_stcore/health')"]

CMD ["streamlit", "run", "app.py"]
