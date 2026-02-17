# ADR-001: Asset architecture and extensibility

- **Status:** Accepted
- **Date:** 2026-02-17
- **Authors:** Yannick Vinkesteijn

## Context

pluginlake is the standard setup for a data station in a federated lakehouse. We need to decide how Dagster assets are structured and how data stations with custom needs can extend or override the default pipeline.

## Decision

**pluginlake ships core assets and is extensible by external repos.**

### Core assets in pluginlake

The `pluginlake` package includes a standard set of assets that every data station needs (e.g. OMOP ingestion, quality checks, common transformations). These live in `pluginlake.assets` and are registered via `pluginlake.definitions`.

### Extensibility model

Data stations that need custom assets have two options:

1. **Import and extend**: Create a separate repo/package that depends on `pluginlake`, import the core assets, and add station-specific assets alongside them:

    ```python
    from dagster import Definitions
    from pluginlake.definitions import core_assets

    from station_x.assets import custom_asset_a, custom_asset_b

    defs = Definitions(assets=[*core_assets, custom_asset_a, custom_asset_b])
    ```

2. **Use only core**: Use `pluginlake` directly if the standard assets are sufficient. No custom repo needed.

### What this means for the code

- `pluginlake.assets` contains core assets shared by all stations.
- `pluginlake.definitions` provides a `Definitions` object and exposes `core_assets` for reuse.
- `pluginlake.core` and `pluginlake.utils` provide shared logic (resources, IO, helpers) usable by both core and custom assets.
- Each data station is a **Dagster code location**, either using `pluginlake.definitions` directly or a custom definitions module.

### Container architecture

| Container | Image | Purpose |
|-----------|-------|---------|
| dagster-code-server | `pluginlake.Dockerfile` (or custom) | Loads asset definitions via gRPC |
| dagster-webserver | `dagster-webserver.Dockerfile` | Web UI, no source code |
| dagster-daemon | `dagster-webserver.Dockerfile` | Schedules, sensors, run queue |
| pluginlake | `pluginlake.Dockerfile` | FastAPI service |

## Alternatives considered

### Separate assets into their own package

Every station gets its own repo from the start, pluginlake is only a library. Rejected because it adds overhead for stations that just need the standard setup (the majority of cases). The extensibility path is still available when needed.

### Config-driven asset selection

Use configuration to toggle which assets are active. Rejected because it couples all station logic into one package and makes testing harder. Code-level composition is more explicit and flexible.

## Consequences

- pluginlake must export its core assets in a way that external repos can import and compose them.
- Custom stations depend on `pluginlake` as a package (PyPI or git dependency).
- Each station's `workspace.yaml` points to its own code-server, allowing the central dagster UI to display multiple stations.
