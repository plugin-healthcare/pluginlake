set dotenv-load := true

# Default recipe: show available commands
default:
    @just --list

init:
    uv sync --all-groups --all-extras
    uv run pre-commit install
    mkdir -p .data

test:
    uv run pytest --cov=pluginlake

lint:
    uv run ruff check .
    uv run ty check .

secure:
    uv run uv-secure

ci: lint test secure

docs: docs-openapi
    uv run zensical serve

# Build docs to site/ (for CI/deployment)
docs-build: docs-openapi
    uv run zensical build

# Export OpenAPI schema to docs/openapi.json
docs-openapi:
    uv run python scripts/export_openapi.py

pre-commit:
    uv run pre-commit run --all-files

# --- Docker ---

_compose := "docker compose -f deploy/compose/docker-compose.dev.yaml"

# Start dev environment (all services)
dev-up *args='':
    {{ _compose }} up --build {{ args }}

# Stop dev environment
dev-down *args='':
    {{ _compose }} down {{ args }}

# Start datastation dashboard with its API dependency
dev-datastation *args='':
    {{ _compose }} up --build pluginlake-ui {{ args }}

_compose_central := "docker compose -f deploy/compose/docker-compose.central.yaml"

# Start central dashboard (separate compose)
dev-central *args='':
    {{ _compose_central }} up --build {{ args }}

# Start only the API (pluginlake + postgres)
dev-api *args='':
    {{ _compose }} up --build pluginlake {{ args }}

_smoke-compose := "-f deploy/compose/docker-compose.dev.yaml -f deploy/compose/docker-compose.smoke.yaml"

# Run smoke test against running stack
smoke-test:
    uv run python scripts/smoke_test.py

# Start isolated stack, run smoke test, tear down (clean volumes)
smoke-test-full:
    docker compose {{ _smoke-compose }} up -d
    uv run python scripts/smoke_test.py; rc=$?; docker compose {{ _smoke-compose }} down -v; exit $rc

# Start local dev with titanic example (no Docker)
dev-local:
    uv run dg dev -f examples/titanic.py

# Start production environment
up *args='':
    docker compose -f deploy/compose/docker-compose.yaml up --build {{ args }}

# Stop production environment
down *args='':
    docker compose -f deploy/compose/docker-compose.yaml down {{ args }}
