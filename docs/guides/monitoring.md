# Monitoring

A station can collect metrics of its own services in Prometheus, so an operator can see whether the station is healthy and connect it to central monitoring (vantage6-ops).
The design is described in [ADR-010](../decisions/adr-010-station-monitoring-prometheus.md).

## Overview

Monitoring has 3 components, which run as containers next to the other services:

- **Prometheus** scrapes the metrics, keeps a local history and pushes them to central monitoring when configured.
- **postgres-exporter** exposes the health of PostgreSQL to Prometheus.
- **cAdvisor** exposes the memory and CPU use of the containers of this stack.

The API also exposes its own metrics on an internal port.
Dashboards and alerting are part of the central monitoring in vantage6-ops, not of the station.

## What is collected

| Job | Source | Examples |
|-----|--------|----------|
| `pluginlake` | API metrics on the internal port `9464` | `pluginlake_http_requests_total`, `pluginlake_http_request_duration_seconds`, `pluginlake_http_exceptions_total` |
| `postgres` | postgres-exporter | `pg_up`, connections, database size, locks, WAL |
| `cadvisor` | cAdvisor, only this stack's containers | `container_memory_usage_bytes`, `container_cpu_usage_seconds_total`, `container_last_seen` |
| `prometheus` | Prometheus itself | scrape and remote-write health |

API metrics are labelled with the route template (`/assets/{asset_id}`), the HTTP method and the status code, never with the raw path or query string.
Per-table Postgres metrics and container labels are switched off, so no patient data or free user input ends up in a metric.

## Configuration

Monitoring is a core component of the production stack and starts with `just up`.
Configure it in the `[monitoring]` section of `pluginlake.toml`, which `just setup` writes to `compose.env`:

```toml
[monitoring]
station_id = "ds-001"          # value of the `station` label on every metric
# cadvisor = false             # when the host already runs cAdvisor (e.g. a vantage6 host stack)
# remote_write_url = "https://plugin.dhd.nl/prometheus/api/v1/write"
```

Prometheus publishes no port.
Open `https://prometheus.<domain>` behind the sign-in (see [Edge](docker.md#edge)) and check that all targets are up under *Status > Targets*.
The exporter logs in with the secret `postgres_exporter_password`, a read-only `pg_monitor` role that `pluginlake-db-init` creates; see [secrets](docker.md#secrets).

The `/metrics` endpoint of the API is only reachable by Prometheus over the compose network, not through the public API or from the host.
cAdvisor runs on a separate `monitoring` network shared only with Prometheus, and `cadvisor = false` keeps the container from starting.

In the dev stack (`just dev-up`, `pluginlake up`) set `enabled = true` to start the compose profile `monitoring`, and Prometheus is published on loopback only at <http://127.0.0.1:9090> (change the host port with `PROMETHEUS_PORT`).

## Connect to central monitoring

Metrics are pushed outbound with Prometheus `remote_write`, the same model vantage6-ops uses for its nodes.

1. Set `remote_write_url` and the username issued by the central monitoring in `[monitoring]` in `pluginlake.toml`:

    ```toml
    [monitoring]
    remote_write_url = "https://..."
    remote_write_username = "..."
    ```

2. The password is a Docker secret, not part of `pluginlake.toml`: put it in the file `secrets/prometheus_remote_write_password` in the node data folder (`PLUGINLAKE_HOME`), or set `PROMETHEUS_REMOTE_WRITE_PASSWORD` in `deploy/compose/.env` in the dev stack.
   Prometheus reads it from `/run/secrets/prometheus_remote_write_password` and refuses to start if the password is found in its environment.
3. Run `just up` again. The Prometheus log shows `remote_write enabled to <scheme>://<host>` (path and query are not logged).

The URL must use `https://` and must not contain credentials (`user:pass@host`); the configuration is refused otherwise.
Every sample carries the `station` external label, so the central side can tell stations apart.
A central Prometheus that can reach the station can alternatively federate from `/federate` on the station's Prometheus.

## Missing container metrics

cAdvisor runs without `privileged`.
On some hosts (certain cgroup v2 or storage setups) a few container metrics, such as disk I/O, stay empty.
Only then enable `privileged` for cAdvisor with a local override file, and keep it to the hosts that need it:

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

Alternatively set `[monitoring] cadvisor = false` and run cAdvisor in the host stack.

## Configuration reference

| Setting | Where | Default | Description |
|---------|-------|---------|-------------|
| `enabled` | `[monitoring]` | `false` | Only for `pluginlake up`: start the `monitoring` profile. The production compose always runs it. |
| `station_id` | `[monitoring]` | `pluginlake` | `station` label on every metric (`[A-Za-z0-9._-]`). |
| `cadvisor` | `[monitoring]` | `true` | Collect container metrics with cAdvisor. |
| `remote_write_url` | `[monitoring]` | unset | Central remote-write endpoint. |
| `remote_write_username` | `[monitoring]` | unset | Basic-auth username for remote write. |
| `retention` | `[monitoring]` | `15d` | Local retention. |
| `PROMETHEUS_REMOTE_WRITE_PASSWORD` | compose secrets env | empty | Basic-auth password, mounted as a Docker secret. |
| `PROMETHEUS_PORT` | shell / `.env` | `9090` | Loopback host port of Prometheus. |
| `PLUGINLAKE_METRICS_ENABLED` | API env | `true` | Record API metrics and serve them on the metrics port. |
| `PLUGINLAKE_METRICS_PORT` | API env | `9464` | Internal metrics port of the API. |

The scrape configuration lives in `deploy/monitoring/prometheus/`: add a job by adding a file to `scrape.d/`.
