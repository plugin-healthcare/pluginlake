#!/bin/sh
# Renders the pluginlake Prometheus config and starts Prometheus (ADR-010).
#
# Environment:
#   PROMETHEUS_STATION_ID              value of the `station` label (default: pluginlake)
#   PROMETHEUS_SCRAPE_CADVISOR         false/0/no/off skips the cAdvisor job (default: true)
#   PROMETHEUS_COMPOSE_PROJECT         compose project whose containers cAdvisor reports
#   PROMETHEUS_RETENTION               local retention (default: 15d)
set -eu

SRC_DIR=/etc/prometheus/pluginlake
OUT_DIR=/tmp/prometheus-config
CONFIG="$OUT_DIR/prometheus.yml"

fail() {
    echo "prometheus-entrypoint: $*" >&2
    exit 1
}

# Labels and paths end up in YAML; only allow characters that need no quoting or escaping.
require_safe() {
    case "$2" in
        "" | *[!A-Za-z0-9._-]*) fail "$1 must be non-empty and contain only [A-Za-z0-9._-], got '$2'" ;;
    esac
}

export PROMETHEUS_STATION_ID="${PROMETHEUS_STATION_ID:-pluginlake}"
require_safe PROMETHEUS_STATION_ID "$PROMETHEUS_STATION_ID"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/scrape.d"
cp "$SRC_DIR/prometheus.yml" "$CONFIG"
cp "$SRC_DIR"/scrape.d/*.yml "$OUT_DIR/scrape.d/"

case "$(printf '%s' "${PROMETHEUS_SCRAPE_CADVISOR:-true}" | tr '[:upper:]' '[:lower:]')" in
    false | 0 | no | off) scrape_cadvisor=false ;;
    true | 1 | yes | on) scrape_cadvisor=true ;;
    *) fail "PROMETHEUS_SCRAPE_CADVISOR must be true or false, got '$PROMETHEUS_SCRAPE_CADVISOR'" ;;
esac

if [ "$scrape_cadvisor" = "false" ]; then
    rm "$OUT_DIR/scrape.d/cadvisor.yml"
    echo "prometheus-entrypoint: cAdvisor scraping disabled"
else
    project="${PROMETHEUS_COMPOSE_PROJECT:-}"
    require_safe PROMETHEUS_COMPOSE_PROJECT "$project"
    sed -i "s/__COMPOSE_PROJECT__/$project/" "$OUT_DIR/scrape.d/cadvisor.yml"
fi

exec /bin/prometheus \
    --config.file="$CONFIG" \
    --storage.tsdb.path=/prometheus \
    --storage.tsdb.retention.time="${PROMETHEUS_RETENTION:-15d}" \
    "$@"
