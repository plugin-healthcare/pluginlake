# Using pluginlake as a package

This guide shows how to use `pluginlake` as a dependency in your own data station project. You get the core assets and utilities out of the box, and can add your own custom assets alongside them.

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

Create a `definitions.py` that combines pluginlake assets with your own:

```python
# my_station/definitions.py

from dagster import Definitions
from pluginlake.assets.omop import omop_condition, omop_observation

from my_station.assets.patient_summary import patient_summary

defs = Definitions(
    assets=[omop_condition, omop_observation, patient_summary],
)
```

You pick exactly which core assets you need — not every station uses all of them.

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
