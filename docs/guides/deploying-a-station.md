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

[[projects]]
name = "my-project"
# Dev: a local checkout, mounted and editable-installed into the images.
path = "../my-project"

# [[projects]]
# name = "other-project"
# Prod: a pinned spec, no local checkout needed.
# source = "other-project @ git+https://github.com/org/other-project@v1.0.0"
```

Exactly one of `path` or `source` must be set per project. See `src/pluginlake/deploy/config.py` for the full schema.

## Bring the station up

The CLI is part of the base install: `pip install pluginlake` (in a checkout: `uv sync`).
Docker with the Compose plugin and a running Docker daemon are required.
The commands check this first and tell you what is missing.

From a core checkout, with the projects available at the paths in `pluginlake.toml`:

```bash
uv run pluginlake up
```

This builds the images, starts the stack in the background, installs the configured projects, wires their contributions, and returns once the services are healthy.
Running it again on a running stack leaves it unchanged.
Add `--attach` to follow the logs afterwards, or `--no-build` to skip rebuilding the images. Once it is healthy:

| Service | URL |
|---------|-----|
| Dashboard (Streamlit) | <http://localhost:8501> |
| Dagster (pipelines and assets) | <http://localhost:3000> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| API health | <http://localhost:8000/health> |

Verify that the configured projects conform to the plugin contract and are wired correctly:

```bash
uv run pluginlake verify
```

Check which services are running and healthy (exit code 1 if any is not), and read their logs:

```bash
uv run pluginlake status
uv run pluginlake logs dagster -f
```

Stop the station.
`down` never removes volumes or data:

```bash
uv run pluginlake down
```

## Onboarding a new project

Scaffold a conformant project package, implement its assets and routers, then add it to `pluginlake.toml`:

```bash
uv run pluginlake project new --name my-project
```

Without `--name` the command asks for the name, the directory and the catalog.

Add a `[[projects]]` entry pointing at the new checkout (or its pinned source) and run `pluginlake up` again. To try a complete project first, run `uv run pluginlake project demo`, which scaffolds a small demo project into `.pluginlake/` and starts the stack with it. The `pluginlake-ehds-demo` repository is a larger worked example.
