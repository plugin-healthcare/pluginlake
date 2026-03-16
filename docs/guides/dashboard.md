# Dashboard

pluginlake includes two Streamlit dashboards: a **datastation dashboard** for monitoring a single data station, and a **central dashboard** for aggregating data across multiple stations.

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

### Running locally

```bash
# With Docker (recommended)
just dev-up          # Starts all services including the dashboard
just dev-up-headless # Starts backend services only (no dashboard)

# Without Docker
cd src/pluginlake-ui/datastation
streamlit run app.py
```

The dashboard is available at `http://localhost:8501`.

### Configuration

The dashboard uses pydantic-settings with the `DASHBOARD_` environment prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_API_URL` | `http://pluginlake:8000` | pluginlake API base URL |
| `DASHBOARD_API_TIMEOUT` | `30` | API request timeout in seconds |
| `DASHBOARD_DAGSTER_URL` | `http://localhost:3000/asset-groups` | Link to the Dagster UI |
| `DASHBOARD_DATASTATION_ID` | `ds-local-001` | Unique identifier for this station |
| `DASHBOARD_DATASTATION_NAME` | `demo-1` | Display name shown in the sidebar |
| `DASHBOARD_ASSETS_DIR` | `/app/assets` | Path to brand assets (logo, images) |

### Architecture

The dashboard follows a layered structure:

```
src/pluginlake-ui/datastation/
├── app.py              # Streamlit entrypoint, navigation, sidebar
├── client.py           # HTTP client wrapping the pluginlake API
├── config.py           # Pydantic settings
├── backend/            # Data fetching functions per domain
│   ├── catalog.py
│   ├── fhir.py
│   ├── ingestion.py
│   ├── metadata.py
│   ├── pipelines.py
│   └── statistics.py
├── components/         # Reusable UI components
│   ├── catalog_detail.py
│   ├── data_flow.py
│   ├── fhir_charts.py
│   ├── ingestion_form.py
│   ├── metadata_view.py
│   ├── omop_charts.py
│   └── status.py
└── pages/              # Streamlit multipage app pages
    ├── 0_Introductie.py
    ├── 1_Overview.py
    ├── 1_Data_Catalog.py
    ├── 2_Pipelines.py
    ├── 2_OMOP_Statistics.py
    ├── 4_FHIR.py
    └── 5_Data_Ingestion.py
```

All data flows through the FastAPI API. The dashboard never accesses DuckLake or Dagster directly.

## Central dashboard

The central dashboard aggregates information from multiple data stations.
It is a separate Streamlit app under `src/pluginlake-ui/central/`.

```bash
just dev-central
```

The central dashboard is available at `http://localhost:8502`.
