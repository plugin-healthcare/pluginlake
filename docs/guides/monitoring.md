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
| `prometheus` | Prometheus itself | scrape health |

API metrics are labelled with the route template (`/assets/{asset_id}`), the HTTP method and the status code, never with the raw path or query string.
Per-table Postgres metrics and container labels are switched off, so no patient data or free user input ends up in a metric.

## Configuration

Monitoring is a core component of the production stack and starts with `just up`.
Configure it in the `[monitoring]` section of `pluginlake.toml`, which `just setup` writes to `compose.env`:

```toml
[monitoring]
station_id = "ds-001"          # value of the `station` label on every metric
# cadvisor = false             # when the host already runs cAdvisor (e.g. a vantage6 host stack)
# publish = "10.0.0.5:9090"    # host address and port for a scraper on the private network
```

Prometheus is published on the host only on `127.0.0.1:9090`, so only processes on the VM can reach it directly.
Open `https://prometheus.<domain>` behind the sign-in (see [Edge](docker.md#edge)) and check that all targets are up under *Status > Targets*.
The exporter logs in with the secret `postgres_exporter_password`, a read-only `pg_monitor` role that `pluginlake-db-init` creates; see [secrets](docker.md#secrets).

The `/metrics` endpoint of the API is only reachable by Prometheus over the compose network, not through the public API or from the host.
cAdvisor runs on a separate `monitoring` network shared only with Prometheus, and `cadvisor = false` keeps the container from starting and removes a running one on the next `just up`.
cAdvisor has no access to the Docker socket itself.
It reads the Docker API through `docker-socket-proxy`, which only allows the read-only calls cAdvisor needs (version, info and the details of one container) and is only reachable from cAdvisor.

In the dev stack (`just dev-up`, `pluginlake up`) set `enabled = true` to start the compose profile `monitoring`, and Prometheus is published on loopback only at <http://127.0.0.1:9090> (change the host port with `PROMETHEUS_PORT`).

## Connect to your own monitoring

Metrics stay on the station.
A hospital that wants them in its own system (for example Azure Monitor managed Prometheus) can do this without changes to the station.

- **Run your own agent on the VM.**
  A Prometheus or Alloy agent that you operate scrapes `127.0.0.1:9090/federate` and forwards the samples with its own `remote_write`.
  This only needs outbound HTTPS, which fits hospital firewalls, and the authentication to your system (such as Entra ID for Azure Monitor) stays in your agent.
- **Let your system scrape the station.**
  Set `publish` in `[monitoring]` to an address of the VM on the private network, run `just setup` and `just up` again, and let your Prometheus federate from `/federate` there.
  Use a private interface and not `0.0.0.0`: the endpoint has no authentication of its own.

Both routes only need `pluginlake.toml`, the compose files stay unchanged.

Sending metrics from the station to a central place is not supported yet, and how a station would authenticate to it is decided together with the processing hub work.

## Missing container metrics

cAdvisor runs without `privileged` and mounts only the cgroup tree and the Docker image metadata, both read-only.
It reports memory, CPU and the containers that are running, and has the disk, disk I/O and network metric groups switched off.
On some hosts (certain cgroup v2 or storage setups) a few container metrics stay empty.
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

cAdvisor turns unhealthy when it reports no Docker Compose container at all on the host, so on a host with other Compose stacks the check does not notice when only this station's containers are missing.
A known cause is the containerd image store of Docker (the default on new installations of Docker Engine 29 and later, shown as `Storage Driver: overlayfs` in `docker info`).
cAdvisor can only read those containers through the containerd socket, which gives full control over every container, so pluginlake does not mount it and `privileged` does not help.
On such a host set `[monitoring] cadvisor = false`, or switch Docker back to the classic image store as described in the [Docker documentation](https://docs.docker.com/engine/storage/containerd/).

## Configuration reference

| Setting | Where | Default | Description |
|---------|-------|---------|-------------|
| `enabled` | `[monitoring]` | `false` | Only for `pluginlake up`: start the `monitoring` profile. The production compose always runs it. |
| `station_id` | `[monitoring]` | `pluginlake` | `station` label on every metric (`[A-Za-z0-9._-]`). |
| `cadvisor` | `[monitoring]` | `true` | Run the cAdvisor container for container metrics (Docker Compose only). |
| `retention` | `[monitoring]` | `15d` | Local retention. |
| `publish` | `[monitoring]` | `127.0.0.1:9090` | Host address and port on which Prometheus is published. |
| `PROMETHEUS_PORT` | shell / `.env` | `9090` | Loopback host port of Prometheus. |
| `PLUGINLAKE_METRICS_ENABLED` | API env | `true` | Record API metrics and serve them on the metrics port. |
| `PLUGINLAKE_METRICS_PORT` | API env | `9464` | Internal metrics port of the API. |

The scrape configuration lives in `deploy/monitoring/prometheus/`: add a job by adding a file to `scrape.d/`.
