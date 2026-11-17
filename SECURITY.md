# Security policy

## Reporting a vulnerability

Do not open a public issue for a security problem.
Report it privately through GitHub: on the repository's **Security** tab, choose **Report a vulnerability**.
We acknowledge a report within five working days and keep you informed about the fix and its release.

Please include the affected version, the steps to reproduce, and the impact you expect.

## Supported versions

pluginlake is in early development (0.x).
Security fixes are made on `main` and released as a new version; only the latest release is supported.

## Security measures

The measures, how operators can verify them, and their known limitations are described in the documentation: [docs/guides/security.md](docs/guides/security.md).
In short:

- Releases come only from a tag on `main` that matches the package version. The release workflow builds the container images, scans them with Trivy, signs them with cosign (keyless) and attaches an SBOM and build provenance. Only after every check passes do the images get their version tag, and an existing tag is never moved.
- Stations run the images pinned by digest, from the images lock in the installed package. The Python package is published to PyPI with trusted publishing and provenance attestations.
- GitHub Actions are pinned to full version tags and run with minimal permissions. Images are scanned on every pull request, on `main` and daily.
- Every service of the production stack runs with a read-only root filesystem, without Linux capabilities, with `no-new-privileges` and as a non-root user. cAdvisor is the documented exception.
- Only the API is published on all interfaces. Databases, the Dagster code server and the Marquez API are not reachable from the host, and passwords are Docker secrets.

The API has no authentication yet. Until it does, restrict access to the API port at the network level.
