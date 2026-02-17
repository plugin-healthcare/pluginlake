# pluginlake

Federated datalake for data stations.

## Quickstart

```bash
# Clone and install
git clone https://github.com/plugin-healthcare/pluginlake.git
cd pluginlake
just init
```

## Development

```bash
just test         # Run tests
just lint         # Run ruff + ty
just pre-commit   # Run all pre-commit hooks
just docs         # Serve documentation locally
```

See [docs/develop-guidelines.md](docs/develop-guidelines.md) for full development guidelines.

## Stack

- **API:** FastAPI
- **Data:** DuckLake, Polars
- **Orchestration:** Dagster
- **Infrastructure:** Docker, Kubernetes, Traefik, PostgreSQL
- **UI:** Streamlit (FastAPI backend)

## Sources

- [x] https://github.com/DutchHospitalData/vantage6-ops
- [x] https://github.com/DutchHospitalData/plugin-blob-proxy.git
- https://github.com/DutchHospitalData/pluginSHIRE
- https://github.com/DutchHospitalData/pluginlake
- https://github.com/dkapitan/dagster-data-station
- https://github.com/dkapitan/srdp
- https://github.com/dkapitan/jortt-report
