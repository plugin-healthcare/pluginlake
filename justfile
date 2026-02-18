set dotenv-load := true

# Default recipe: show available commands
default:
    @just --list

init:
    uv sync --all-groups --all-extras
    uv run pre-commit install

test:
    uv run pytest --cov=pluginlake

lint:
    uv run ruff check .
    uv run ty check .

secure:
    uv run uv-secure

ci: lint test secure

docs:
    uv run zensical serve

pre-commit:
    uv run pre-commit run --all-files

# --- Docker ---

# Start dev environment
dev-up *args='':
    docker compose -f deploy/compose/docker-compose.dev.yaml up --build {{ args }}

# Stop dev environment
dev-down *args='':
    docker compose -f deploy/compose/docker-compose.dev.yaml down {{ args }}

# Start local dev with titanic example (no Docker)
dev-local:
    uv run dagster dev -f examples/titanic.py

# Start production environment
up *args='':
    docker compose -f deploy/compose/docker-compose.yaml up --build {{ args }}

# Stop production environment
down *args='':
    docker compose -f deploy/compose/docker-compose.yaml down {{ args }}
