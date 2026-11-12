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
    uv run rumdl check docs README.md CONTRIBUTING.md AGENTS.md {{ args }}

# Auto-fix markdown lint issues
docs-lint-fix:
    uv run rumdl fmt docs README.md CONTRIBUTING.md AGENTS.md

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
    {{ _compose }} --profile ui --profile lineage down {{ args }}

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

# Production compose: the node data folder (secrets, compose.env) is prepared by `pluginlake setup`
home := env("PLUGINLAKE_HOME", justfile_directory() / ".pluginlake")
_compose_prod := "docker compose --env-file " + home + "/compose.env -f deploy/compose/docker-compose.yaml"

# Prepare the node from pluginlake.toml (folders, secrets, compose.env) in a container as the host user. Pass --dev for development defaults
setup *args='':
    #!/usr/bin/env bash
    set -euo pipefail
    # Created here so docker does not create the mount source as root.
    mkdir -p "{{ home }}"
    chmod 700 "{{ home }}"
    docker build --quiet -f deploy/docker/pluginlake.Dockerfile -t pluginlake-setup . > /dev/null
    if [[ " {{ args }} " == *" --dev "* ]]; then
        command -v mkcert > /dev/null || { echo "mkcert is required for --dev: https://github.com/FiloSottile/mkcert" >&2; exit 1; }
        mkdir -p "{{ home }}/tls"
        chmod 700 "{{ home }}/tls"
        if [[ ! -f "{{ home }}/tls/cert.pem" ]]; then
            mkcert -install
            mkcert -cert-file "{{ home }}/tls/cert.pem" -key-file "{{ home }}/tls/key.pem" pluginlake.localhost "*.pluginlake.localhost"
            cp "$(mkcert -CAROOT)/rootCA.pem" "{{ home }}/tls/ca.pem"
        fi
    fi
    docker run --rm --user "$(id -u):$(id -g)" --network none --cap-drop ALL --read-only \
        -v "{{ home }}:/pluginlake-home" -v "{{ justfile_directory() }}/pluginlake.toml:/pluginlake.toml:ro" \
        pluginlake-setup pluginlake setup --config /pluginlake.toml --home /pluginlake-home --host-home "{{ home }}" {{ args }}

# Start the production stack
up *args='':
    just setup
    {{ _compose_prod }} up --build {{ args }}

# Start the stack with development defaults (pluginlake.localhost, secrets also in secrets.env)
up-dev *args='':
    just setup --dev
    {{ _compose_prod }} up --build {{ args }}

# Stop the production stack
down *args='':
    {{ _compose_prod }} down {{ args }}

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
