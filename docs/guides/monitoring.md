# Monitoring

A station can collect metrics of its own services in Prometheus, so an operator can see whether the station is healthy and connect it to central monitoring (vantage6-ops).
The design is described in [ADR-010](../decisions/adr-010-station-monitoring-prometheus.md).

## What is collected

| Job | Source | Examples |
|-----|--------|----------|
| `pluginlake` | API metrics on the internal port `9464` | `pluginlake_http_requests_total`, `pluginlake_http_request_duration_seconds`, `pluginlake_http_exceptions_total` |
| `postgres` | postgres-exporter | `pg_up`, connections, database size, locks, WAL |
| `cadvisor` | cAdvisor, only this stack's containers | `container_memory_usage_bytes`, `container_cpu_usage_seconds_total`, `container_last_seen` |
| `prometheus` | Prometheus itself | scrape and remote-write health |

API metrics are labelled with the route template (`/assets/{asset_id}`), the HTTP method and the status code, never with the raw path or query string.
Per-table Postgres metrics and container labels are switched off, so no patient data or free user input ends up in a metric.

## Enable monitoring

Add a `[monitoring]` section to `pluginlake.toml`:

```toml
[monitoring]
enabled = true
station_id = "ds-001"          # value of the `station` label on every metric
# cadvisor = false             # when the host already runs cAdvisor (e.g. a vantage6 host stack)
# remote_write_url = "https://plugin.dhd.nl/prometheus/api/v1/write"
```

`pluginlake up` then starts the compose profile `monitoring` (Prometheus, postgres-exporter, cAdvisor).
`pluginlake down` always stops it.

Prometheus is published on loopback only: <http://127.0.0.1:9090> (change the host port with `PROMETHEUS_PORT`).
Check that all targets are up under *Status > Targets* or with:

```bash
curl -s http://127.0.0.1:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health}'
```

The `/metrics` endpoint of the API is not reachable through the public API port (`8000`) or from the host; only Prometheus reaches it over the compose network.
cAdvisor runs on a separate `monitoring` network shared only with Prometheus, so the application containers cannot reach its API.

## Connect to central monitoring

Metrics are pushed outbound with Prometheus `remote_write`, the same model vantage6-ops uses for its nodes.

1. Set `remote_write_url` in `pluginlake.toml` (or `PROMETHEUS_REMOTE_WRITE_URL` in the env file).
2. Copy `deploy/compose/.env.monitoring.example` to `deploy/compose/.env.monitoring` and fill in the credentials issued by the central monitoring:

    ```bash
    PROMETHEUS_REMOTE_WRITE_USERNAME=...
    PROMETHEUS_REMOTE_WRITE_PASSWORD=...
    ```

3. Run `pluginlake up` again. The Prometheus log shows `remote_write enabled to <scheme>://<host>` (path and query are not logged).

The URL must use `https://` and must not contain credentials (`user:pass@host`); `pluginlake up` and Prometheus refuse it otherwise.
Only the `prometheus` service reads `.env.monitoring`; it is gitignored.
Every sample carries the `station` external label, so the central side can tell stations apart.
A central Prometheus that can reach the station can alternatively federate from `/federate` on the station's Prometheus.

## Production compose

The production compose (`deploy/compose/docker-compose.yaml`) has the same profile, started manually:

```bash
docker compose -f deploy/compose/docker-compose.yaml --profile monitoring up -d
```

Set `PROMETHEUS_STATION_ID` in `deploy/compose/.env.monitoring`.
Copy `deploy/compose/.env.postgres-exporter.example` to `deploy/compose/.env.postgres-exporter` and set the exporter credentials (`DATA_SOURCE_USER`, `DATA_SOURCE_PASS`); only postgres-exporter reads that file.
Use a dedicated read-only database user for the exporter:

```sql
CREATE ROLE monitoring LOGIN PASSWORD '...' IN ROLE pg_monitor;
```

## Configuration reference

| Setting | Where | Default | Description |
|---------|-------|---------|-------------|
| `enabled` | `[monitoring]` | `false` | Start the `monitoring` compose profile. |
| `station_id` | `[monitoring]` | `pluginlake` | `station` label on every metric (`[A-Za-z0-9._-]`). |
| `cadvisor` | `[monitoring]` | `true` | Collect container metrics with cAdvisor. |
| `remote_write_url` | `[monitoring]` | unset | Central remote-write endpoint. |
| `PROMETHEUS_REMOTE_WRITE_USERNAME` / `_PASSWORD` | `.env.monitoring` | unset | Basic-auth credentials for remote write. |
| `PROMETHEUS_RETENTION` | `.env.monitoring` | `15d` | Local retention. |
| `PROMETHEUS_PORT` | shell / `.env` | `9090` | Loopback host port of Prometheus. |
| `PLUGINLAKE_METRICS_ENABLED` | API env | `true` | Record API metrics and serve them on the metrics port. |
| `PLUGINLAKE_METRICS_HOST` | API env | `127.0.0.1` | Bind address of the metrics port; the compose files set `0.0.0.0` so Prometheus can reach it. |
| `PLUGINLAKE_METRICS_PORT` | API env | `9464` | Internal metrics port of the API. |

The scrape configuration lives in `deploy/monitoring/prometheus/`: `prometheus.yml` plus one file per job in `scrape.d/`.
Add a job by adding a file there.
Dashboards and alerting are part of the central monitoring in vantage6-ops, not of the station.
