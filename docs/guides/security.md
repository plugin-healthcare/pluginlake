# Security

This page describes how pluginlake protects a station and its release pipeline, and where those measures stop.
To report a vulnerability, see [SECURITY.md](https://github.com/plugin-healthcare/pluginlake/blob/main/SECURITY.md).

## Summary

| Area | Measure | Enforced by |
|------|---------|-------------|
| Source of images | Our images are built, scanned, signed and attested only by the release workflow, from a tag on `main` | `release.yaml`, tag ruleset for `v*` |
| Image references | Every image a station runs is pinned by digest | Images lock, `test_compose_hardening.py` |
| Base images | `dhi.io` hardened images, pinned by digest | `test_compose_hardening.py`, Dependabot |
| CI | Actions pinned to commit SHAs (version as comment), `permissions: {}` by default | `test_workflows.py`, zizmor/actionlint locally |
| Vulnerabilities | Trivy on every pull request, on `main` and daily; `uv audit` daily | `images.yaml`, `security.yaml` |
| Runtime | Read-only root filesystem, all capabilities dropped, `no-new-privileges`, non-root users | Shared `x-hardening` block, `test_compose_hardening.py` |
| Network | Only the API on all interfaces; UIs on loopback; databases, code server and Marquez API not published | `test_compose_hardening.py` |
| Secrets | Docker secrets as files, never in a container's environment or config (except the Dagster and Marquez processes, see below) | Compose, `pluginlake up` checks |
| Package | PyPI trusted publishing (OIDC), provenance attestations | `release.yaml` |

## Release pipeline

A release starts with a tag `v<version>` on `main` that equals `project.version` in `pyproject.toml`; the workflow refuses a tag that is not on `main` or differs from the version.
GitHub runs the workflow from the tagged commit, so someone who can create a `v*` tag could change that check in the tagged commit; a tag ruleset that lets only maintainers create `v*` tags is what makes "only from `main`" hold (see [one-time setup](../development/develop-guidelines.md#one-time-setup)).
The workflow creates a draft GitHub Release with the changelog section as notes; a maintainer publishes it.
Publishing runs these jobs, see [release process](../development/develop-guidelines.md#release-process):

1. Each image is built from the tagged commit for `linux/amd64` and pushed **by digest only** to `ghcr.io/plugin-healthcare/pluginlake/<image>` (`api`, `dagster-webserver`, `ui-central`, `ui-datastation`).
2. Trivy scans the pushed digest; a CRITICAL vulnerability with an available fix stops the release.
3. The digest is signed with cosign, keyless: the certificate binds the signature to `release.yaml` at that tag through GitHub's OIDC token, recorded in the public Sigstore transparency log.
4. An SPDX SBOM (Syft) and a SLSA build provenance attestation are attached to the digest in the registry, also signed through Sigstore.
5. Only when every image passed, the promote job verifies each signature and tags the digest with the version. A tag that already exists must point at the same digest; the workflow never moves a tag. A re-run reuses tagged images instead of rebuilding them.
6. The digests are written into the images lock of the package, and the wheel and sdist are built, attested and published to PyPI with trusted publishing: no API token exists that could leak.

Every action in these jobs is pinned to a commit SHA, so a moved tag of an action cannot run code in the jobs that sign, attest or publish.

`pluginlake up` only starts images from the images lock of the installed version, each referenced as `name:version@sha256:digest`, so the digest decides what runs, not the tag.

### Verify an image

Operators can check that an image comes from this pipeline before running it:

```bash
VERSION=<version from images.json>
IMAGE=ghcr.io/plugin-healthcare/pluginlake/api@sha256:<digest from images.json>
cosign verify "$IMAGE" \
  --certificate-identity "https://github.com/plugin-healthcare/pluginlake/.github/workflows/release.yaml@refs/tags/v${VERSION}" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
gh attestation verify "oci://$IMAGE" --repo plugin-healthcare/pluginlake                     # provenance
gh attestation verify "oci://$IMAGE" --repo plugin-healthcare/pluginlake --predicate-type https://spdx.dev/Document/v2.3   # SBOM
```

The images lock of the installed package is `pluginlake/deploy/stack/images.json`.
The wheel can be verified the same way with `gh attestation verify <wheel> --repo plugin-healthcare/pluginlake`.

### Registries

Stations pull from two registries:

- `ghcr.io/plugin-healthcare/pluginlake/*`: our images. When the packages are public, no login is needed. While they are private, every node logs in with a GitHub account that can read the packages and a personal access token (classic) with only `read:packages`: `docker login ghcr.io -u <user>` with the token as password. Use a dedicated machine account per node and revoke its token when the node leaves.
- `dhi.io`: the Postgres image (and the base images at build time). Docker Hardened Images need a Docker account: `docker login dhi.io` with a read-only access token.

## Vulnerability scanning

- Pull requests build all four images and fail on a CRITICAL vulnerability with a fix (Trivy, `--ignore-unfixed`).
- On `main` and daily at 05:30 UTC, the same build reports fixable HIGH and CRITICAL findings to the Security tab (code scanning), so new CVEs in unchanged images show up there.
- `uv audit` checks the locked Python dependencies daily.
- Dependabot proposes updates for Python dependencies, the action versions, the base image digests and the compose image digests.

## Runtime hardening

All services of the production stack (`src/pluginlake/deploy/stack/docker-compose.yaml`) merge one shared block and set a non-root user:

```yaml
x-hardening: &hardening
  read_only: true                         # read-only root filesystem
  cap_drop: [ALL]                         # no Linux capabilities
  security_opt: ["no-new-privileges:true"] # no setuid escalation
  tmpfs:
    - /tmp
```

| Service | User | Writable |
|---------|------|----------|
| postgres, marquez-db | 70 (postgres) | data volume, tmpfs `/var/run/postgresql` and `/tmp` |
| pluginlake (API), dagster-code-server | 65532 | data volume `/app/.data`, `/tmp` |
| dagster-webserver, dagster-daemon | 65532 | `/tmp` |
| dashboard-datastation | 65532 | `/tmp` |
| prometheus, postgres-exporter | 65534 (nobody) | data volume (Prometheus), `/tmp` |
| marquez, marquez-web | 65534 (nobody) | `/tmp` |
| cadvisor | root | none (read-only) |

The images are built for this: dependencies and bytecode are installed at build time, and the DuckDB extensions (`ducklake`, `postgres`) are part of the `api` image, so nothing is downloaded at runtime.
Container logs are rotated (5 × 10 MB per container).

### Resource limits

Every DuckDB connection is limited to 2 GB of memory and 10 GB of spill space on the data volume (`DUCKLAKE_MEMORY_LIMIT`, `DUCKLAKE_MAX_TEMP_DIRECTORY_SIZE`; see [DuckLake](../reference/ducklake.md#resource-limits)).
A query over the limits fails with a clear error (HTTP 507 in the API) instead of exhausting the host, and the API container has a memory cap of 4 GB (`PLUGINLAKE_API_MEM_LIMIT`) as a backstop.
The Dagster code server has no container cap: Polars work in assets is not covered by the DuckDB limits, and a cap could kill valid runs.

### Ports

| Port | Service | Bound to |
|------|---------|----------|
| 8000 | API | all interfaces |
| 3000 | Dagster UI | 127.0.0.1 |
| 8501 | Dashboard | 127.0.0.1 |
| 9090 | Prometheus | 127.0.0.1 |
| 3001 | Marquez UI | 127.0.0.1 |
| — | PostgreSQL, Marquez database and API, Dagster code server, exporters | not published |

The UIs have no authentication of their own; reach them through an SSH tunnel.

### Secrets

Passwords are files in the station's `secrets/` directory (`0700`, files `0644`), mounted read-only at `/run/secrets/<name>`; see [secrets](docker.md#secrets).
They are not part of any container's configuration (`docker inspect`) or environment file.
pluginlake reads them through its settings; Postgres and the exporter through `*_FILE` variables.

## Limitations

These are known gaps; they are documented here rather than hidden.

- **API authentication** is not part of this release. Authentication and authorization follow in a separate step (ADR-006, ADR-008); until then, restrict access to port 8000 at the network level.
- **cAdvisor runs as root with its default capabilities and can reach the Docker socket**, because it reads the Docker state of the host. Its read-only mount of `/var/run` does not stop it from connecting to `/var/run/docker.sock`, so a compromised cAdvisor controls the Docker daemon and with that the host. It keeps a read-only filesystem and `no-new-privileges` and is on its own network, but treat it as host-level access. Switch it off with `[monitoring] cadvisor = false` when it is not needed.
- **Dagster and Marquez need their database password in the process environment**: `dagster.yaml` and `marquez.yml` can only read it from there. A launcher exports it for that process only; it is not in the container configuration, but is visible in `/proc` to the same user inside that container.
- **Secret files are world-readable inside their directory**, so the non-root container users can read them. The `0700` directory keeps other host users out; root on the host can read them, as with every Compose secret. They are not encrypted at rest.
- **Tags in GHCR are not immutable at the registry level.** The release workflow never moves a tag, and stations run by digest, but a maintainer with write access to the packages could. Restrict package write access to the release workflow and maintainers.
- **Actions are pinned to commit SHAs**, so a moved tag (as happened with `aquasecurity/trivy-action` in March 2026) does not change what runs. A pinned commit can still contain a vulnerability or malicious code; Dependabot proposes new versions, and an update is reviewed like any other change.
- **"Only from `main`" depends on the tag ruleset.** The workflow checks that the tag is on `main`, but it runs from the tagged commit, so someone who can create `v*` tags could remove that check. Restrict `v*` tag creation to maintainers.
- **Trivy fails only on CRITICAL vulnerabilities that have a fix.** Unfixed and lower-severity findings are reported (HIGH on `main` and daily) but do not block a release.
- **Only `linux/amd64`** images are built.
- **Projects** cannot be installed in the production stack yet; it runs the core only. The dev stack (`pluginlake up --dev`) installs projects at start and is not hardened in the same way: it keeps a writable filesystem and runs some services as root (it does drop all capabilities and sets `no-new-privileges`).
- **Third-party images** (Postgres, Marquez, Prometheus, the exporter, cAdvisor) are pinned by digest and kept up to date by Dependabot, but not rebuilt, signed or scanned by us: Trivy in CI scans our own four images only.
- The **Postgres base image requires a Docker account** (`dhi.io`) on every station.
