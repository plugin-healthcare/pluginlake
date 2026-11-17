# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e

# Dev Dockerfile for the pluginlake Streamlit dashboards (hot reload).
# APP selects the dashboard (src/pluginlake-ui/<APP>), PORT its port:
#   datastation (default): --build-arg APP=datastation --build-arg PORT=8501
#   central:               --build-arg APP=central --build-arg PORT=8502

FROM dhi.io/python:3.13-debian13-dev@sha256:cc070c5f483069c53e251a63d114f1f17af806f257a67c9106967247d3ee092a

COPY --from=dhi.io/uv:0-debian13-dev@sha256:e0f9b9c9bf4b95ddd229886777961a28ebbfd38fb00d96f2ae58eb2b843b1de6 /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --only-group dashboard

COPY . .

ARG APP=datastation
ARG PORT=8501

ENV PATH="/app/.venv/bin:$PATH" \
    UI_APP=${APP} \
    STREAMLIT_SERVER_PORT=${PORT} \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_RUN_ON_SAVE=true

EXPOSE ${PORT}

CMD ["sh", "-c", "exec streamlit run \"src/pluginlake-ui/${UI_APP}/app.py\""]
