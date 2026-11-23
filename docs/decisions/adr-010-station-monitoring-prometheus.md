# ADR-010: Station monitoring with Prometheus

- **Status:** Proposed
- **Date:** 2026-11-03
- **Authors:** pluginlake team

## TL;DR

Each data station runs its own Prometheus as the compose profile `monitoring`, switched on with `[monitoring] enabled = true` in `pluginlake.toml`.
It scrapes the pluginlake API (`/metrics` on an internal port), Postgres (via postgres-exporter) and the station's containers (via cAdvisor).
Metrics stay on the station.
Central monitoring is out of scope for now, and the mechanism by which a station would send metrics is decided together with the processing hub and Nuts work.
Labels are bounded by design, so neither patient data nor free user input can end up in a metric.
The compose profile is the choice for a node that runs Docker Compose, see [Choices per runtime](#choices-per-runtime) for other runtimes.

## Context

Operators need to see whether a station is healthy without logging in to the host, and the metrics may later feed a central monitoring.

vantage6-ops (ADR 002, ADR 004 in DutchHospitalData/vantage6-ops) sets the constraints we follow:

- Hospital firewalls only allow outbound HTTPS, so a central Prometheus cannot scrape a node.
- Exporters are only reachable on the local Docker network, never via host ports.
- Every sample carries host-identifying external labels (`agb`, `host` there) so the central side can tell nodes apart.
- cAdvisor is trimmed: no container labels are shipped, and only the stack's own containers are reported.
- Grafana dashboards and alerting live centrally and are out of scope for the node.

## Decision

### Components (compose profile `monitoring`)

| Service | Image | Reachable |
|---|---|---|
| `prometheus` | `quay.io/prometheus/prometheus` v3, pinned by digest | `127.0.0.1:9090` only |
| `postgres-exporter` | `quay.io/prometheuscommunity/postgres-exporter`, pinned by digest | compose network only |
| `cadvisor` | `ghcr.io/google/cadvisor` (same version as vantage6-ops), pinned by digest | compose network only |

Upstream images are used because the hardened `dhi.io/prometheus` image has no shell (needed for the config entrypoint) and trails upstream.

We run a full Prometheus rather than an Alloy agent like vantage6-ops: the station keeps a local, queryable history (default 15 days) that also works when no central monitoring is connected, and it can later forward or be federated when central monitoring is decided.

### Choices per runtime

The components above are what a node on Docker Compose needs, because a bare-metal VM has no cloud provider that supplies container metrics or a metrics store.
Other runtimes make some of them unnecessary (the runtime tiers are described in [ADR-012](adr-012-core-platform-and-deployment.md)):

| Component | Docker Compose (VM) | Kubernetes (self-hosted or managed) |
|---|---|---|
| API metrics and postgres-exporter | Scraped by the station Prometheus | Same endpoints, scraped by the cluster Prometheus |
| Container metrics | Our `cadvisor` container, only for Compose | The kubelet already serves cAdvisor metrics, so no container of ours |
| Local Prometheus | Optional, switched on with `[monitoring] enabled`, gives local history without central monitoring | A self-hosted cluster runs its own Prometheus, a managed cluster can use the provider's monitoring |

The `cadvisor` service is therefore part of the Compose deployment only, and a Kubernetes deployment scrapes the kubelet instead.
An agent such as Grafana Alloy can replace the local Prometheus where no local history is needed, but it runs the same cAdvisor code and needs the same host access, so it does not remove the cAdvisor privileges.

### API metrics

The API records `pluginlake_http_requests_total`, `pluginlake_http_request_duration_seconds`, `pluginlake_http_requests_in_progress` and `pluginlake_http_exceptions_total` in a pure ASGI middleware (`pluginlake.api.metrics`).

- `route` is the matched route template (`/assets/{asset_id}`), never the raw path; unmatched requests share `route="unmatched"`.
- `method` is limited to the standard HTTP methods (others become `OTHER`); `status` is the numeric code; `exception` is the exception class name.
- The metrics are served by a separate HTTP server on `PLUGINLAKE_METRICS_PORT` (default `9464`), which compose only `expose`s. The public API port has no `/metrics` route. It binds to loopback by default; the compose files set `PLUGINLAKE_METRICS_HOST=0.0.0.0` so Prometheus can scrape it over the compose network.
- Failing to bind the metrics port logs an error; the API keeps running. Prometheus then reports the `pluginlake` target as down.

### Scrape configuration

`deploy/monitoring/prometheus/` holds `prometheus.yml` and one file per job in `scrape.d/`.
An entrypoint script renders the final config at container start:

- `station` external label from `PROMETHEUS_STATION_ID` (`[monitoring] station_id`).
- `scrape.d/cadvisor.yml` is dropped when `PROMETHEUS_SCRAPE_CADVISOR=false`, for hosts that already run cAdvisor (such as a vantage6 host stack).
- cAdvisor series are kept only for containers of this compose project.

The remote-less setup means the only monitoring secret is the postgres-exporter password, a Docker Compose secret (see the [Docker guide](../guides/docker.md#secrets)): mounted under `/run/secrets/` in its own service only, never in a container environment.
A central Prometheus that can reach the station may federate from `/federate`.

### No patient data, no free input in labels

- API labels are bounded as described above.
- postgres-exporter runs without the per-table collectors (`stat_user_tables`, `statio_user_tables`), because table names can derive from uploaded files. Query text (`stat_statements`) stays off.
- cAdvisor stores no container labels except the compose project and service, which are then dropped after filtering.

## Consequences

- Operators get station health locally (`http://127.0.0.1:9090`). A host address on a private network can be set with `[monitoring] publish`, and the endpoint has no authentication of its own, so it must not face the internet.
- cAdvisor needs read access to host paths and `/dev/kmsg`, like in vantage6-ops; it can be switched off with `[monitoring] cadvisor = false`. Its access to the Docker socket makes it host-privileged, so it runs on a separate `monitoring` network that only Prometheus joins.
- The central side should add `agb`/`host` labels per station if it needs them; the station only sends `station`.
- Dagster metrics are not collected yet; this can be added as another `scrape.d` job.
- Dashboards and alerting are out of scope and belong in vantage6-ops.
