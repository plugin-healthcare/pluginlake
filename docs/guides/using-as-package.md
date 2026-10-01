# Using pluginlake as a package

This guide shows how to use `pluginlake` as a dependency in your own data station project. You get the core platform — the DuckLake IO manager, shared utilities, the FastAPI gateway, and the plugin host — and can add your own custom assets alongside it.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) as your package manager

## Project setup

Create a new project for your data station:

```bash
uv init my-station
cd my-station
```

Add `pluginlake` as a dependency:

```bash
uv add pluginlake --git https://github.com/plugin-healthcare/pluginlake.git
```

## Define your assets

Create your station-specific assets in your project. For example:

```python
# my_station/assets/patient_summary.py

import polars as pl
from dagster import asset


@asset(description="Custom patient summary for this station.")
def patient_summary() -> pl.DataFrame:
    ...
```

## Compose definitions

Create a `definitions.py` that combines your assets into a Dagster
`Definitions` object:

```python
# my_station/definitions.py

from dagster import Definitions

from my_station.assets.patient_summary import patient_summary

defs = Definitions(
    assets=[patient_summary],
)
```

Core provides the platform — the DuckLake IO manager, the FastAPI gateway, and
the plugin host — while your assets and any installed project packages provide
the domain logic. Clinical models such as OMOP and FHIR are not bundled in core;
they ship as project packages that plug in via the `pluginlake.projects` entry
point (see [Deploying a Station](deploying-a-station.md) and ADR-009).

## Using pluginlake utilities

Beyond assets, `pluginlake` provides shared utilities you can use in your own code:

```python
from pluginlake.utils.logger import get_logger
from pluginlake.config import Settings
```

## Run locally

Start the Dagster UI to test your assets:

```bash
uv run dagster dev -m my_station.definitions
```

Open `http://localhost:3000` to see both the core and custom assets in the asset graph.

## Deploy with Docker

Create a `Dockerfile` for your station:

```dockerfile
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

FROM python:3.13-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"
```

Then in your `docker-compose.yaml`, run it as a dagster code-server:

```yaml
services:
  my-station-code-server:
    build: .
    command:
      [
        "dagster", "code-server", "start",
        "-h", "0.0.0.0",
        "-p", "4000",
        "-m", "my_station.definitions",
      ]
    ports:
      - "4000:4000"
```

The central dagster-webserver connects to your code-server via `workspace.yaml`:

```yaml
load_from:
  - grpc_server:
      host: my-station-code-server
      port: 4000
```
