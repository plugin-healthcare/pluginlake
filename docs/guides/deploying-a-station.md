# Deploying a station

A pluginlake **station** is the standardized platform (PostgreSQL, Dagster, the FastAPI gateway, and the dashboard) plus one or more **projects** that provide the domain logic. The platform is the same everywhere; each deployment differs only in which projects it runs. This guide shows how projects are onboarded and how to bring a station up.

## How onboarding works

Projects plug into a station through a single entry point — no files are copied or edited by hand (ADR-009).

![How projects relate to the data station](../assets/images/project-datastation.png)

1. A project package declares a `ProjectManifest` and registers it on the `pluginlake.projects` entry-point group in its `pyproject.toml`:

    ```toml
    [project.entry-points."pluginlake.projects"]
    ehds-demo = "ehds_demo.manifest:manifest"
    ```

   The manifest names the project's DuckLake catalog, its asset namespace, and the Dagster code locations and API routers it contributes.

2. The operator lists the projects to deploy in a `pluginlake.toml` station config.

3. `pluginlake up` reads that config, installs the listed projects into the standardized images at container start, and core **discovers** them via the entry point — mounting their code locations in Dagster and their routers on the API gateway automatically.

Because wiring happens at install time through the entry point, the platform image never has to know about any specific project ahead of time.

## The station config

`pluginlake.toml` is the operator-owned deployment surface. Each project is either a local checkout (`path`, for development) or a pinned install spec (`source`, for production):

```toml
[station]
endpoint_url = "http://localhost:8000"

[monitoring]
enabled = true          # start Prometheus and exporters (compose profile `monitoring`)
station_id = "ds-001"

[[projects]]
name = "ehds-demo"
# Dev: a local sibling checkout, mounted and editable-installed into the images.
path = "../pluginlake-ehds-demo"

# [[projects]]
# name = "ehds-demo"
# Prod: a pinned spec, no local checkout needed.
# source = "pluginlake-ehds-demo @ git+https://github.com/plugin-healthcare/pluginlake-ehds-demo@v0.1.0"
```

Exactly one of `path` or `source` must be set per project. See `src/pluginlake/deploy/config.py` for the full schema.
The `[monitoring]` section is optional and described in the [monitoring guide](monitoring.md).

## Bring the station up

The station runs as a production node:

```bash
just up -d
```

This prepares the node data folder, builds the images and starts the stack.
The production stack does not install the `[[projects]]` of `pluginlake.toml` yet, because its images are read-only and have no install step at start.
Projects are installed by `pluginlake up`, which drives the development compose stack.
Every application is reached on its own subdomain of `[node] domain` and sits behind the login, for example `https://console.<domain>`, `https://dagster.<domain>`, `https://lineage.<domain>` and `https://api.<domain>/docs`.
The [Docker guide](docker.md#edge) describes the edge, the roles and the secrets.

Verify that the configured projects conform to the plugin contract and are wired correctly:

```bash
uv run pluginlake verify
```

Stop the station with `just down`.
Data stays in the node data folder and is never removed by stopping or restarting the station.

## Lineage with Marquez

Every station runs [Marquez](https://marquezproject.ai) as the receiver for OpenLineage events (ADR-007).
Core registers the `openlineage_sensor`, which sends one OpenLineage event per materialized asset: upstream assets as inputs, the DuckLake table as output, and the schema, row count and column lineage from the asset metadata.
Events contain no data values, projects do not need to register anything, and a failed send only logs a warning.
The Marquez UI is available at `https://lineage.<domain>` after login.

Give each node its own namespace, so jobs from different stations stay apart:

```toml
[station]
lineage_namespace = "ds-local-001"
```

## Onboarding a new project

Scaffold a conformant project package, implement its assets and routers, then add it to `pluginlake.toml`:

```bash
uv run pluginlake init my-project
```

Add a `[[projects]]` entry pointing at the new checkout (or its pinned source) and run `pluginlake up` again. The `pluginlake-ehds-demo` repository is a complete worked example of a project package.
