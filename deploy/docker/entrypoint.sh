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
