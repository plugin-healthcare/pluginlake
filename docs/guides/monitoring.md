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

In the dev compose Prometheus is published on loopback only: <http://127.0.0.1:9090> (change the host port with `PROMETHEUS_PORT`).
The production compose publishes no port: open `https://prometheus.<domain>` behind the sign-in (see [Edge](docker.md#edge)).
Check that all targets are up under *Status > Targets* or with:

```bash
curl -s http://127.0.0.1:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health}'
```

The `/metrics` endpoint of the API is not reachable through the public API port (`8000`) or from the host; only Prometheus reaches it over the compose network.
cAdvisor runs on a separate `monitoring` network shared only with Prometheus, so the application containers cannot reach its API.

## Connect to central monitoring

Metrics are pushed outbound with Prometheus `remote_write`, the same model vantage6-ops uses for its nodes.

1. Set `remote_write_url` in `pluginlake.toml` (or `PROMETHEUS_REMOTE_WRITE_URL` in the env file).
2. Copy `deploy/compose/.env.monitoring.example` to `deploy/compose/.env.monitoring` and set the username issued by the central monitoring:

    ```bash
    PROMETHEUS_REMOTE_WRITE_USERNAME=...
    ```

   The password is a Docker secret, not part of `.env.monitoring`: set `PROMETHEUS_REMOTE_WRITE_PASSWORD` in `deploy/compose/.env` (dev, `pluginlake up`) or the file `secrets/prometheus_remote_write_password` in the production data folder (`PLUGINLAKE_HOME`).
   Prometheus reads it from `/run/secrets/prometheus_remote_write_password` and refuses to start if the password is found in its environment.
3. Run `pluginlake up` again. The Prometheus log shows `remote_write enabled to <scheme>://<host>` (path and query are not logged).

The URL must use `https://` and must not contain credentials (`user:pass@host`); `pluginlake up` and Prometheus refuse it otherwise.
Only the `prometheus` service reads `.env.monitoring`; it is gitignored.
Every sample carries the `station` external label, so the central side can tell stations apart.
A central Prometheus that can reach the station can alternatively federate from `/federate` on the station's Prometheus.

## Production compose

In the production compose (`deploy/compose/docker-compose.yaml`) monitoring is a core component and starts with `just up`.
`pluginlake setup` writes the station label, the cAdvisor switch and the remote-write URL from `[monitoring]` in `pluginlake.toml` to `compose.env`.
The exporter logs in as the fixed role `monitoring` with the secret `postgres_exporter_password`, which `pluginlake-db-init` creates as a `pg_monitor` role; see [secrets](docker.md#secrets).
Compose refuses to start when `POSTGRES_EXPORTER_PASSWORD` or `PROMETHEUS_REMOTE_WRITE_PASSWORD` is not set (the latter may be empty).
Use a dedicated read-only database user for the exporter:

```sql
CREATE ROLE monitoring LOGIN PASSWORD '...' IN ROLE pg_monitor;
```

## Missing container metrics

cAdvisor runs without `privileged` and only gets read access to `/dev/kmsg` and the host paths it needs.
On some hosts (certain cgroup v2 or storage setups) a few container metrics, such as disk I/O or filesystem usage, stay empty.
Check *Status > Targets* and query `container_memory_usage_bytes` first.
Only if metrics are missing on that host, enable `privileged` for cAdvisor with a local override file next to the production compose:

```yaml
# deploy/compose/docker-compose.local.yaml (gitignored)
services:
  cadvisor:
    privileged: true
```

```bash
docker compose --env-file .pluginlake/compose.env \
  -f deploy/compose/docker-compose.yaml -f deploy/compose/docker-compose.local.yaml up -d
```

`privileged` gives the container full access to the host devices.
cAdvisor already has root-equivalent access through the Docker socket, so this adds little risk, but keep it to the hosts that need it.
`pluginlake up` does not load extra compose files; on such a host, set `[monitoring] cadvisor = false` and run cAdvisor in the host stack instead.

## Configuration reference

| Setting | Where | Default | Description |
|---------|-------|---------|-------------|
| `enabled` | `[monitoring]` | `false` | Only for the development flow `pluginlake up`: start the `monitoring` profile. The production compose always runs it. |
| `station_id` | `[monitoring]` | `pluginlake` | `station` label on every metric (`[A-Za-z0-9._-]`). |
| `cadvisor` | `[monitoring]` | `true` | Collect container metrics with cAdvisor. |
| `remote_write_url` | `[monitoring]` | unset | Central remote-write endpoint. |
| `PROMETHEUS_REMOTE_WRITE_USERNAME` | `.env.monitoring` | unset | Basic-auth username for remote write. |
| `PROMETHEUS_REMOTE_WRITE_PASSWORD` | compose secrets env | empty | Basic-auth password, mounted as a Docker secret. |
| `PROMETHEUS_RETENTION` | `.env.monitoring` | `15d` | Local retention. |
| `PROMETHEUS_PORT` | shell / `.env` | `9090` | Loopback host port of Prometheus. |
| `PLUGINLAKE_METRICS_ENABLED` | API env | `true` | Record API metrics and serve them on the metrics port. |
| `PLUGINLAKE_METRICS_HOST` | API env | `127.0.0.1` | Bind address of the metrics port; the compose files set `0.0.0.0` so Prometheus can reach it. |
| `PLUGINLAKE_METRICS_PORT` | API env | `9464` | Internal metrics port of the API. |

The scrape configuration lives in `deploy/monitoring/prometheus/`: `prometheus.yml` plus one file per job in `scrape.d/`.
Add a job by adding a file there.
Dashboards and alerting are part of the central monitoring in vantage6-ops, not of the station.
