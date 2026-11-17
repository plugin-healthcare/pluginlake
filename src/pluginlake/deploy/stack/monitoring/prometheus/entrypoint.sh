#!/bin/sh
# Renders the pluginlake Prometheus config and starts Prometheus (ADR-010).
#
# Environment:
#   PROMETHEUS_STATION_ID              value of the `station` label (default: pluginlake)
#   PROMETHEUS_SCRAPE_CADVISOR         false/0/no/off skips the cAdvisor job (default: true)
#   PROMETHEUS_COMPOSE_PROJECT         compose project whose containers cAdvisor reports
#   PROMETHEUS_REMOTE_WRITE_URL        central remote-write endpoint (optional, https:// only, no '@')
#   PROMETHEUS_REMOTE_WRITE_USERNAME   basic-auth username (optional)
#   PROMETHEUS_REMOTE_WRITE_PASSWORD   never in the environment: compose mounts it as the
#                                      secret /run/secrets/prometheus_remote_write_password
#   PROMETHEUS_RETENTION               local retention (default: 15d)
set -eu

SRC_DIR=/etc/prometheus/pluginlake
OUT_DIR=/tmp/prometheus-config
CONFIG="$OUT_DIR/prometheus.yml"
PASSWORD_FILE=/run/secrets/prometheus_remote_write_password

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

# Values written as double-quoted YAML strings must not break out of the quotes.
reject_unquotable() {
    case "$2" in
        *[\"\\[:space:]]*) fail "$1 must not contain quotes, backslashes or whitespace" ;;
    esac
}

[ -z "${PROMETHEUS_REMOTE_WRITE_PASSWORD:-}" ] ||
    fail "PROMETHEUS_REMOTE_WRITE_PASSWORD must not be set in the container env (e.g. .env.monitoring); it is a compose secret"

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

url="${PROMETHEUS_REMOTE_WRITE_URL:-}"
if [ -n "$url" ]; then
    case "$url" in
        https://*) ;;
        *) fail "PROMETHEUS_REMOTE_WRITE_URL must start with https://" ;;
    esac
    reject_unquotable PROMETHEUS_REMOTE_WRITE_URL "$url"
    # Credentials in the URL would end up in logs; they belong in the username/password variables.
    case "$url" in
        *@*) fail "PROMETHEUS_REMOTE_WRITE_URL must not contain '@'; use PROMETHEUS_REMOTE_WRITE_USERNAME/PASSWORD" ;;
    esac
    {
        echo ""
        echo "remote_write:"
        echo "  - url: \"$url\""
    } >>"$CONFIG"
    username="${PROMETHEUS_REMOTE_WRITE_USERNAME:-}"
    if [ -n "$username" ]; then
        reject_unquotable PROMETHEUS_REMOTE_WRITE_USERNAME "$username"
        [ -s "$PASSWORD_FILE" ] ||
            fail "a remote-write username needs a password: set PROMETHEUS_REMOTE_WRITE_PASSWORD in the compose secrets env file"
        {
            echo "    basic_auth:"
            echo "      username: \"$username\""
            echo "      password_file: $PASSWORD_FILE"
        } >>"$CONFIG"
    fi
    # Log only scheme and host; path and query may carry tokens.
    host="${url#*://}"
    host="${host%%/*}"
    host="${host%%\?*}"
    host="${host%%#*}"
    echo "prometheus-entrypoint: remote_write enabled to ${url%%://*}://$host"
else
    echo "prometheus-entrypoint: remote_write disabled, metrics stay local"
fi

exec /bin/prometheus \
    --config.file="$CONFIG" \
    --storage.tsdb.path=/prometheus \
    --storage.tsdb.retention.time="${PROMETHEUS_RETENTION:-15d}" \
    "$@"
