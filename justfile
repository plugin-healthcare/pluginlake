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

# Same checks as CI: no auto-fix, formatting checked, ty warnings fail
lint:
    uv run ruff check --no-fix .
    uv run ruff format --check .
    uv run ty check .

secure:
    uv audit --locked --preview-features audit-command

ci: lint test secure

docs port='8100': docs-openapi
    uv run zensical serve -a localhost:{{ port }}

# Build docs to site/ (for CI/deployment)
docs-build: docs-openapi
    uv run zensical build

# Export OpenAPI schema to docs/openapi.json
docs-openapi:
    uv run python scripts/export_openapi.py

# Serve the docs locally (docs only, no OpenAPI export)
serve port='8100':
    uv run zensical serve -a localhost:{{ port }}

# Lint markdown (no line-length rule: one sentence per line)
docs-lint *args='':
    uv run rumdl check docs README.md CONTRIBUTING.md AGENTS.md SECURITY.md {{ args }}

# Auto-fix markdown lint issues
docs-lint-fix:
    uv run rumdl fmt docs README.md CONTRIBUTING.md AGENTS.md SECURITY.md

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

# Stop dev environment (all profiles)
dev-down *args='':
    {{ _compose }} --profile ui --profile lineage --profile monitoring down {{ args }}

_compose_central := "docker compose -f deploy/compose/docker-compose.central.yaml"

# Start central dashboard (separate compose)
dev-central *args='':
    {{ _compose_central }} up --build {{ args }}

_smoke-compose := 'env -i HOME="$HOME" PATH="$PATH" PLUGINLAKE_ENV_FILE=smoke.env docker compose --env-file deploy/compose/smoke.env --env-file deploy/compose/smoke.secrets.env -f deploy/compose/docker-compose.dev.yaml -f deploy/compose/docker-compose.smoke.yaml'

# Run smoke test against running stack
smoke-test:
    uv run python scripts/smoke_test.py

# Start isolated stack, run smoke test, tear down (clean volumes)
smoke-test-full:
    {{ _smoke-compose }} up -d postgres dagster pluginlake
    uv run python scripts/smoke_test.py; rc=$?; {{ _smoke-compose }} down -v; exit $rc

# Start local dev with titanic example (no Docker)
dev-local:
    uv run dg dev -f examples/titanic.py

# Production stack (packaged in src/pluginlake/deploy/stack) with images built from this
# checkout. Config from deploy/compose/.env.production, passwords (Docker secrets) from
# deploy/compose/.env.production.secrets. Stations use `pluginlake up` with released images.
_prod_env := "PLUGINLAKE_STACK_DIR=" + justfile_directory() + "/src/pluginlake/deploy/stack PLUGINLAKE_IMAGE_API=pluginlake/api:local PLUGINLAKE_IMAGE_DAGSTER_WEBSERVER=pluginlake/dagster-webserver:local PLUGINLAKE_IMAGE_UI_DATASTATION=pluginlake/ui-datastation:local"
_compose_prod := _prod_env + " docker compose --project-directory deploy/compose --env-file deploy/compose/.env.production --env-file deploy/compose/.env.production.secrets -f src/pluginlake/deploy/stack/docker-compose.yaml -f deploy/compose/docker-compose.build.yaml"

# Start production environment (built locally)
up *args='':
    {{ _compose_prod }} up --build {{ args }}

# Stop production environment
down *args='':
    {{ _compose_prod }} --profile ui --profile lineage --profile monitoring down {{ args }}

# Build the four release images locally (same Dockerfiles as the image workflow)
images:
    docker build -f deploy/docker/api.Dockerfile -t pluginlake/api:local .
    docker build -f deploy/docker/dagster-webserver.Dockerfile -t pluginlake/dagster-webserver:local .
    docker build -f deploy/docker/ui.Dockerfile --build-arg APP=datastation --build-arg PORT=8501 -t pluginlake/ui-datastation:local .
    docker build -f deploy/docker/ui.Dockerfile --build-arg APP=central --build-arg PORT=8502 -t pluginlake/ui-central:local .

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
