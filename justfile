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

# Start dev environment (all services including dashboards)
dev-up *args='':
    {{ _compose }} --profile ui up --build {{ args }}

# Start dev environment without dashboards
dev-up-headless *args='':
    {{ _compose }} up --build {{ args }}

# Stop dev environment
dev-down *args='':
    {{ _compose }} --profile ui down {{ args }}

_compose_central := "docker compose -f deploy/compose/docker-compose.central.yaml"

# Start central dashboard (separate compose)
dev-central *args='':
    {{ _compose_central }} up --build {{ args }}

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

# --- Infrastructure (OpenTofu) ---

infra_dir := "deploy/infra"

# Install OpenTofu on Ubuntu
infra-install:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v tofu &>/dev/null; then
        echo "OpenTofu already installed: $(tofu version | head -1)"
        exit 0
    fi
    echo "Installing OpenTofu via apt..."
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://get.opentofu.org/opentofu.gpg \
        | sudo tee /etc/apt/keyrings/opentofu.gpg >/dev/null
    curl -fsSL https://packages.opentofu.org/opentofu/tofu/gpgkey \
        | sudo gpg --dearmor -o /etc/apt/keyrings/opentofu-repo.gpg 2>/dev/null
    echo "deb [signed-by=/etc/apt/keyrings/opentofu.gpg,/etc/apt/keyrings/opentofu-repo.gpg] https://packages.opentofu.org/opentofu/tofu/any/ any main" \
        | sudo tee /etc/apt/sources.list.d/opentofu.list >/dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq tofu
    echo "Installed: $(tofu version | head -1)"

# Initialise OpenTofu (download providers)
infra-init:
    cd {{ infra_dir }} && tofu init

# Show planned infrastructure changes
infra-plan:
    cd {{ infra_dir }} && tofu plan

# Apply infrastructure changes
infra-apply:
    cd {{ infra_dir }} && tofu apply

# Destroy all managed infrastructure (CAUTION: All resources (containers, images, blobs, etc.) will be deleted without confirmation!)
infra-destroy:
    cd {{ infra_dir }} && tofu destroy

# Validate configuration files
infra-validate:
    cd {{ infra_dir }} && tofu validate

# Show current infrastructure state
infra-show:
    cd {{ infra_dir }} && tofu show

# Format all .tf files
infra-fmt:
    cd {{ infra_dir }} && tofu fmt -recursive
