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
_compose_prod := "docker compose --env-file " + quote(home / "compose.env") + " -f deploy/compose/docker-compose.yaml"

# Prepare the node from pluginlake.toml (folders, secrets, compose.env) in a container as the host user. A domain below .localhost gets an mkcert certificate
setup *args='':
    #!/usr/bin/env bash
    set -euo pipefail
    # The checkout is the Docker build context, and only .pluginlake/ is kept out of it.
    case "$(realpath -m "{{ home }}")/" in
        "$(realpath "{{ justfile_directory() }}")/.pluginlake/") ;;
        "$(realpath "{{ justfile_directory() }}")"/*) echo "PLUGINLAKE_HOME must be .pluginlake or outside the checkout, so no image can contain its secrets" >&2; exit 1 ;;
    esac
    # Created here so docker does not create the mount source as root.
    mkdir -p "{{ home }}"
    chmod 700 "{{ home }}"
    # PLUGINLAKE_SETUP_IMAGE uses a prebuilt pluginlake image instead of building one.
    image="${PLUGINLAKE_SETUP_IMAGE:-}"
    if [[ -n "$image" ]]; then
        docker pull --quiet "$image" > /dev/null
    else
        image=pluginlake-setup
        docker build --quiet -f deploy/docker/pluginlake.Dockerfile -t "$image" . > /dev/null
    fi
    domain="$(docker run --rm --user "$(id -u):$(id -g)" --network none --cap-drop ALL --read-only \
        -v "{{ justfile_directory() }}/pluginlake.toml:/pluginlake.toml:ro" "$image" \
        python -c 'import tomllib; print(tomllib.load(open("/pluginlake.toml", "rb")).get("node", {}).get("domain") or "")')"
    # The same lock as `pluginlake setup`, so concurrent runs do not mix the files of two certificates.
    command -v flock > /dev/null || { echo "flock (util-linux) is required for just setup" >&2; exit 1; }
    exec 9>> "{{ home }}/.setup.lock"
    flock 9
    if [[ "$domain" == "localhost" || "$domain" == *.localhost ]]; then
        command -v mkcert > /dev/null || { echo "mkcert is required for a .localhost domain: https://github.com/FiloSottile/mkcert" >&2; exit 1; }
        mkdir -p "{{ home }}/tls" "{{ home }}/ca"
        chmod 700 "{{ home }}/tls"
        if [[ ! -f "{{ home }}/tls/cert.pem" || ! -f "{{ home }}/tls/key.pem" || ! -f "{{ home }}/ca/ca.pem" || "$(cat "{{ home }}/tls/cert.domain" 2>/dev/null)" != "$domain" ]]; then
            mkcert -install
            mkcert -cert-file "{{ home }}/tls/cert.pem" -key-file "{{ home }}/tls/key.pem" "$domain" "*.$domain"
            cp "$(mkcert -CAROOT)/rootCA.pem" "{{ home }}/ca/ca.pem"
            echo "$domain" > "{{ home }}/tls/cert.domain"
        fi
    fi
    exec 9>&-
    docker run --rm --user "$(id -u):$(id -g)" --network none --cap-drop ALL --read-only \
        -v "{{ home }}:/pluginlake-home" -v "{{ justfile_directory() }}/pluginlake.toml:/pluginlake.toml:ro" \
        "$image" pluginlake setup --config /pluginlake.toml --home /pluginlake-home --host-home "{{ home }}" {{ args }}

# Start the production stack
up *args='':
    just setup
    {{ _compose_prod }} up --build {{ args }}

# Stop the production stack
# Variables added after a node's last setup are set here, so its older compose.env can still stop the stack.
down *args='':
    CADVISOR_REPLICAS="${CADVISOR_REPLICAS:-0}" PLUGINLAKE_SECRETS_REVISION="${PLUGINLAKE_SECRETS_REVISION:-down}" {{ _compose_prod }} down {{ args }}

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

# --- Scaleway demo VM (OpenTofu, state encrypted in Scaleway Object Storage) ---

demo_infra_dir := "deploy/infra/scaleway-demo"

# Run tofu for the demo VM, e.g. `just demo-tofu plan`. Reads deploy/infra/scaleway-demo/.env and the scw CLI profile
[positional-arguments]
demo-tofu *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ demo_infra_dir }}"
    [[ -f .env ]] || { echo "Copy {{ demo_infra_dir }}/.env.example to .env and fill it in" >&2; exit 1; }
    set -a; source ./.env; set +a
    # The S3 backend reads AWS variables; the Scaleway API key works for Object Storage.
    export AWS_ACCESS_KEY_ID="$(scw config get access-key)"
    export AWS_SECRET_ACCESS_KEY="$(scw config get secret-key)"
    if [[ "${1:-}" == "init" ]]; then
        tofu "$@" -backend-config="bucket=${TOFU_STATE_BUCKET:?set TOFU_STATE_BUCKET in .env}"
    else
        tofu "$@"
    fi

demo_registry := env("DEMO_REGISTRY", "ghcr.io/plugin-healthcare")
demo_ehds_dir := env("DEMO_EHDS_DIR", justfile_directory() / ".." / "pluginlake-ehds-demo")
demo_wheels_dir := env("DEMO_WHEELS_DIR", justfile_directory() / ".agents" / "runbook" / "demo" / "wheels")

# Build the demo images for linux/amd64 and tag them `demo` and with the commit; `just demo-images push` also pushes them
demo-images mode="load":
    #!/usr/bin/env bash
    set -euo pipefail
    [[ "{{ mode }}" == load || "{{ mode }}" == push ]] || { echo "mode must be load or push" >&2; exit 1; }
    sha="$(git rev-parse --short HEAD)$([[ -z "$(git status --porcelain -- src pyproject.toml uv.lock deploy/docker deploy/demo)" ]] || echo -dirty)"
    ehds_sha="$(git -C "{{ demo_ehds_dir }}" rev-parse --short HEAD)"
    mkdir -p .agents/logs "{{ demo_wheels_dir }}"; log=".agents/logs/demo-images-$(date +%Y%m%dT%H%M%S).log"
    echo "pluginlake ${sha}, ehds-demo ${ehds_sha}, log ${log}"
    build() {
        local name="$1"; shift
        echo "== ${name}" | tee -a "$log"
        docker buildx build --platform linux/amd64 --"{{ mode }}" \
            --label org.opencontainers.image.source=https://github.com/plugin-healthcare/pluginlake \
            -t "{{ demo_registry }}/${name}:demo" -t "{{ demo_registry }}/${name}:${sha}" "$@" . >>"$log" 2>&1 \
            || { echo "build of ${name} failed, see ${log}" >&2; tail -20 "$log" >&2; exit 1; }
    }
    build pluginlake -f deploy/docker/pluginlake.Dockerfile
    build pluginlake-dagster-webserver -f deploy/docker/dagster-webserver.Dockerfile
    build pluginlake-ui -f deploy/docker/ui.Dockerfile
    build pluginlake-ehds-demo -f deploy/demo/ehds-demo.Dockerfile --build-context ehds="{{ demo_ehds_dir }}" \
        --build-context wheels="{{ demo_wheels_dir }}" --label "org.pluginlake.ehds-demo.revision=${ehds_sha}"
    echo "done: {{ demo_registry }}/*:demo and :${sha}"

# --- Demo VM operations from a workstation (reads deploy/demo/.env, reaches the VM over Tailscale) ---

_demo_env := 'set -a; source deploy/demo/.env 2>/dev/null || { echo "Copy deploy/demo/.env.example to deploy/demo/.env and fill it in" >&2; exit 1; }; set +a'

# Start, stop or show the demo VM: `just demo-vm-power start|stop|status`
demo-vm-power action="status":
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _demo_env }}
    id="$(scw instance server list name="${DEMO_VM_NAME:-pluginlake-demo}" zone=fr-par-1 -o json | jq -r '.[0].id')"
    case "{{ action }}" in
        start) scw instance server start "$id" zone=fr-par-1 --wait > /dev/null ;;
        stop) scw instance server stop "$id" zone=fr-par-1 --wait > /dev/null ;;
        status) ;;
        *) echo "action must be start, stop or status" >&2; exit 1 ;;
    esac
    scw instance server get "$id" zone=fr-par-1 -o json | jq -r '"\(.name): \(.state)"'

# Copy the demo images and Postgres (dhi.io needs a login) to the VM over SSH, for use with DEMO_PULL=0
demo-images-copy:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _demo_env }}
    mkdir -p .agents/logs
    log=".agents/logs/demo-images-copy-$(date +%Y%m%dT%H%M%S).log"
    tag="${DEMO_TAG:-demo}" reg="${DEMO_REGISTRY:-ghcr.io/plugin-healthcare}" pg="$(grep -o -m1 'dhi.io/postgres:[^ "]*' deploy/compose/docker-compose.yaml)"
    {
        docker pull --quiet --platform linux/amd64 "$pg"
        docker save --platform linux/amd64 "$reg/pluginlake:$tag" "$reg/pluginlake-dagster-webserver:$tag" "$reg/pluginlake-ui:$tag" \
            "$reg/pluginlake-ehds-demo:$tag" "$pg" | gzip -1 | ssh "${DEMO_SSH:?set DEMO_SSH}" 'gunzip | docker load'
        # Restore the image for this machine's own architecture.
        docker pull --quiet "$pg" > /dev/null
    } 2>&1 | tee "$log"

# Check out DEMO_REF (a pushed branch or tag) on the VM and run deploy/demo/vm.sh there, e.g. `just demo-vm up` (bootstrap, certs, serve, up, data, down, ps, logs)
[positional-arguments]
demo-vm *args:
    #!/usr/bin/env bash
    set -euo pipefail
    {{ _demo_env }}
    repo="${DEMO_REPO:-https://github.com/plugin-healthcare/pluginlake.git}" ref="${DEMO_REF:?set DEMO_REF to a pushed branch or tag that contains deploy/demo}"
    # The VM only gets what is pushed, so warn when the local commit is not on the remote ref.
    git fetch --quiet origin "$ref" 2>/dev/null && [[ "$(git rev-parse HEAD)" == "$(git rev-parse FETCH_HEAD)" ]] \
        || echo "Note: the VM runs origin/$ref, which differs from your local HEAD." >&2
    ssh -t "${DEMO_SSH:?set DEMO_SSH}" "set -e
        [ -d pluginlake/.git ] || git clone --quiet $(printf %q "$repo") pluginlake
        cd pluginlake
        git fetch --quiet origin $(printf %q "$ref")
        git checkout --quiet --detach FETCH_HEAD
        echo \"pluginlake $(printf %q "$ref") at \$(git rev-parse --short HEAD)\"
        DEMO_DOMAIN=$(printf %q "${DEMO_DOMAIN:?set DEMO_DOMAIN}") DEMO_REGISTRY=$(printf %q "${DEMO_REGISTRY:-ghcr.io/plugin-healthcare}") DEMO_TAG=$(printf %q "${DEMO_TAG:-demo}") DEMO_PULL=$(printf %q "${DEMO_PULL:-1}") DEMO_FHIR_PATIENTS=$(printf %q "${DEMO_FHIR_PATIENTS:-1000}") deploy/demo/vm.sh $(printf '%q ' "$@")"
