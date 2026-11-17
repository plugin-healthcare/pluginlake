# Dashboard

pluginlake includes a Streamlit **datastation dashboard** for monitoring a single data station.

## Datastation dashboard

The datastation dashboard provides an operational view of one pluginlake instance.
It connects to the FastAPI API and displays pipeline status, data catalog contents, and ingestion tools.

### Pages

| Page | Description |
|------|-------------|
| **Introductie** | Dutch introduction explaining the platform concepts and architecture. |
| **Overview** | KPI cards (pipelines, runs, assets, datasets), asset table with layer and domain tags, recent runs, and data catalog grouped by medallion layer. |
| **Data Catalog** | Browse DuckLake schemas and tables, inspect column metadata and statistics. |
| **Pipelines** | Detailed view of Dagster asset groups and pipeline run history. |
| **OMOP** | OMOP CDM table statistics and row counts. |
| **FHIR** | FHIR resource statistics. |
| **Upload Data** | Upload OMOP CSV or FHIR NDJSON files through the API. |

### Running

In a node the dashboard is the console at `https://console.<domain>` (see the [Getting started](getting-started.md)).
For development:

```bash
just dev-up          # Starts all services including the dashboard
just dev-up-headless # Starts backend services only (no dashboard)
```

The dev dashboard is available at `http://localhost:8501`.

### Configuration

The dashboard uses pydantic-settings with the `DASHBOARD_` environment prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_API_URL` | `http://pluginlake:8000` | pluginlake API base URL |
| `DASHBOARD_API_TIMEOUT` | `30` | API request timeout in seconds |
| `DASHBOARD_DOMAIN` | `pluginlake.localhost` | Domain of the node; the sidebar links to the other web interfaces on its subdomains, for each role the user has. A deployed node gets `[node] domain` from `pluginlake.toml` through `just setup` |
| `DASHBOARD_DATASTATION_ID` | `ds-local-001` | Unique identifier for this station. The default is a development value; set it for each deployed node |
| `DASHBOARD_DATASTATION_NAME` | `demo-1` | Display name shown in the sidebar. The default is a development value; set it for each deployed node |
| `DASHBOARD_ASSETS_DIR` | `/app/assets` | Path to brand assets (logo, images) |

### Architecture

The dashboard code lives in `src/pluginlake-ui/datastation/`: `app.py` (entrypoint, navigation, sidebar), `client.py` (HTTP client), `config.py` (settings), `backend/` (data fetching), `components/` (reusable UI) and `pages/`.
All data flows through the FastAPI API.
The dashboard never accesses DuckLake or Dagster directly.
