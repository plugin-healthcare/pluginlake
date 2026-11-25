#!/usr/bin/env bash
# Runs the pluginlake demo on a tailnet-only VM. Called from a workstation through `just demo-vm <command>`.
#
#   bootstrap  add the user to the docker group and make it the Tailscale operator (once, asks for the sudo password)
#   certs      create the VM-only CA and the wildcard certificate Traefik serves behind Tailscale
#   serve      advertise the Tailscale Services that forward HTTPS to Traefik
#   up         render pluginlake.toml, prepare the node and start the stack from the registry images
#   data       download the Synthea test data that the ehds-demo sensors ingest
#   down | ps | logs [service]
#
# Environment: DEMO_DOMAIN (the tailnet domain, e.g. example.ts.net), DEMO_REGISTRY and DEMO_TAG (optional),
# DEMO_PULL=0 to use images copied with `just demo-images-copy` instead of pulling them.
set -euo pipefail

cd "$(dirname "$0")/../.."
SERVICES=(auth api console dagster lineage prometheus)
HOME_DIR="$PWD/.pluginlake"
# The CA signing key stays outside HOME_DIR, which the setup container mounts read-write.
CA_PRIVATE="${XDG_DATA_HOME:-$HOME/.local/share}/pluginlake-demo/ca"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/pluginlake-demo"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y%m%dT%H%M%S)-${1:-help}.log"
exec > >(tee -a "$LOG") 2>&1
echo "# $(date -Is) vm.sh $* (log: $LOG)"

export DEMO_REGISTRY="${DEMO_REGISTRY:-ghcr.io/plugin-healthcare}"
export DEMO_TAG="${DEMO_TAG:-demo}"
DEMO_PULL="${DEMO_PULL:-1}"
compose() {
    docker compose --env-file "$HOME_DIR/compose.env" \
        -f deploy/compose/docker-compose.yaml -f deploy/demo/docker-compose.demo.yaml "$@"
}
domain() { echo "${DEMO_DOMAIN:?set DEMO_DOMAIN to the tailnet domain, e.g. example.ts.net}"; }

bootstrap() {
    id -nG | grep -qw docker || { sudo usermod -aG docker "$USER"; echo "Added $USER to the docker group: log in again."; }
    # As operator, the user runs `tailscale serve` without sudo.
    sudo tailscale set --operator="$USER"
    docker compose version
}

certs() {
    local d key="$CA_PRIVATE/ca-key.pem" ca="$HOME_DIR/ca/ca.pem"
    local crt="$HOME_DIR/tls/fullchain.pem" leaf_key="$HOME_DIR/tls/privkey.pem"
    d="$(domain)"
    mkdir -p "$HOME_DIR/tls" "$HOME_DIR/ca" "$CA_PRIVATE"
    chmod 700 "$HOME_DIR" "$HOME_DIR/tls" "$CA_PRIVATE"
    # Browsers see Tailscale's certificates; only oauth2-proxy trusts this CA.
    if [[ ! -f "$key" || ! -f "$ca" ]] || ! openssl x509 -checkend 2592000 -noout -in "$ca"; then
        openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 365 \
            -subj "/CN=pluginlake demo VM CA" -keyout "$key" -out "$ca"
        chmod 600 "$key"
        rm -f "$crt"
    fi
    if [[ ! -f "$crt" || ! -f "$leaf_key" || "$(cat "$HOME_DIR/tls/cert.domain" 2>/dev/null)" != "$d" ]] \
        || ! openssl x509 -checkend 2592000 -noout -in "$crt" || ! openssl verify -CAfile "$ca" "$crt" > /dev/null; then
        openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=$d" \
            -keyout "$leaf_key" -out "$HOME_DIR/tls/leaf.csr"
        openssl x509 -req -in "$HOME_DIR/tls/leaf.csr" -CA "$ca" -CAkey "$key" -CAcreateserial \
            -CAserial "$CA_PRIVATE/ca.srl" -days 180 -out "$crt" \
            -extfile <(printf 'subjectAltName=DNS:%s,DNS:*.%s\nextendedKeyUsage=serverAuth\n' "$d" "$d")
        rm "$HOME_DIR/tls/leaf.csr"
        chmod 600 "$leaf_key"
        echo "$d" > "$HOME_DIR/tls/cert.domain"
    fi
    # An own tls.yaml is kept by `pluginlake setup` for domains outside .localhost.
    printf 'tls:\n  certificates:\n    - certFile: /tls/fullchain.pem\n      keyFile: /tls/privkey.pem\n' > "$HOME_DIR/tls/tls.yaml"
    openssl verify -CAfile "$ca" "$crt"
}

serve() {
    # Tailscale keeps the original Host header, which Traefik routes on. The target is an IP so no SNI is sent:
    # Traefik refuses a request whose SNI differs from its Host header.
    for s in "${SERVICES[@]}"; do
        tailscale serve --service="svc:$s" --https=443 https+insecure://127.0.0.1:443
    done
    tailscale serve status
}

up() {
    local d; d="$(domain)"
    local image="$DEMO_REGISTRY/pluginlake-ehds-demo:$DEMO_TAG"
    certs
    # Rendered outside the checkout, where pluginlake.toml is a tracked file.
    sed "s/@DOMAIN@/$d/g" deploy/demo/pluginlake.toml.template > "$HOME_DIR/pluginlake.toml"
    [[ "$DEMO_PULL" == 0 ]] || docker pull --quiet "$image" > /dev/null
    docker run --rm --user "$(id -u):$(id -g)" --network none --cap-drop ALL --read-only \
        -v "$HOME_DIR:/pluginlake-home" -v "$HOME_DIR/pluginlake.toml:/pluginlake.toml:ro" \
        "$image" pluginlake setup --config /pluginlake.toml --home /pluginlake-home --host-home "$HOME_DIR"
    [[ "$DEMO_PULL" == 0 ]] || compose pull --quiet
    local rc=0
    compose up -d --no-build --pull "$([[ "$DEMO_PULL" == 0 ]] && echo missing || echo always)" --wait --wait-timeout 900 || rc=$?
    compose ps -a --format '{{.Service}}\t{{.Status}}'
    if (( rc != 0 )); then
        echo "compose up failed (exit $rc); see \`just demo-vm logs <service>\`." >&2
        exit "$rc"
    fi
    echo "Open https://console.$d from a tailnet device."
}

case "${1:-}" in
    bootstrap) bootstrap ;;
    certs) certs ;;
    serve) serve ;;
    up) up ;;
    data) compose --profile data run --rm --pull "$([[ "$DEMO_PULL" == 0 ]] && echo never || echo always)" demo-data ;;
    down) compose down ;;
    ps) compose ps -a --format '{{.Service}}\t{{.Status}}' ;;
    logs) compose logs --no-color --tail 200 "${@:2}" ;;
    *) sed -n '2,11p' "$0"; exit 1 ;;
esac
