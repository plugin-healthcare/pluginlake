#!/usr/bin/env sh
# Container entrypoint for the standardized pluginlake images.
#
# Installs the project packages listed in $PLUGINLAKE_PROJECTS before launching
# the service, so their `pluginlake.projects` entry points are discoverable and
# core mounts their code locations and routers uniformly (ADR-009). The value is
# a whitespace-separated list of `uv pip install` arguments, so it works the same
# for dev (a local editable path, e.g. `-e /opt/projects/my-project`) and prod
# (a pinned spec, e.g. `my-project @ git+https://.../my-project@v1.2.3`).
set -e

# Ensure the databases named in $PLUGINLAKE_ENSURE_DB (whitespace-separated)
# exist before the service starts. Dagster does not create its own metadata
# database, and the hardened postgres image ignores /docker-entrypoint-initdb.d,
# so we provision them here. Idempotent and safe to run on every boot.
if [ -n "${PLUGINLAKE_ENSURE_DB:-}" ]; then
    echo "[entrypoint] Ensuring databases exist: ${PLUGINLAKE_ENSURE_DB}"
    python - "${PLUGINLAKE_ENSURE_DB}" <<'PYEOF'
import os
import sys

import psycopg2
from psycopg2 import sql

host = os.environ.get("DAGSTER_PG_HOST") or os.environ.get("POSTGRES_HOST", "postgres")
port = os.environ.get("DAGSTER_PG_PORT", "5432")
user = os.environ.get("DAGSTER_PG_USER") or os.environ["POSTGRES_USER"]
password = os.environ.get("DAGSTER_PG_PASSWORD") or os.environ["POSTGRES_PASSWORD"]

conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname="postgres")
conn.autocommit = True
with conn.cursor() as cur:
    for db in sys.argv[1].split():
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
        if cur.fetchone():
            print(f"[entrypoint] database {db!r} already exists")
        else:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
            print(f"[entrypoint] created database {db!r}")
conn.close()
PYEOF
fi

if [ -n "${PLUGINLAKE_PROJECTS:-}" ]; then
    echo "[entrypoint] Installing projects: ${PLUGINLAKE_PROJECTS}"
    # --no-sources: ignore each project's [tool.uv.sources] (dev-only path/pins
    # that don't resolve inside the image); deps come from the already-installed
    # core, the index, and any direct PEP 508 URLs the project declares.
    # Intentionally unquoted: the value expands into multiple install arguments.
    # shellcheck disable=SC2086
    uv pip install --no-sources ${PLUGINLAKE_PROJECTS}
fi

exec "$@"
