"""Images lock of the packaged production stack.

The production compose (``stack/docker-compose.yaml``) refers to our own images
through ``PLUGINLAKE_IMAGE_*`` variables. ``pluginlake up`` fills them from
``stack/images.json``, which the release workflow writes after the images are
pushed, scanned, signed and tagged, and before it builds the package. Every entry
is pinned by digest, so a station runs exactly the images of its release.

In a source checkout the lock is empty: there are no released images to run.

The release workflow writes the lock with::

    python -m pluginlake.deploy.images write --version 0.2.0 --digest api=sha256:... ...
"""

import argparse
import json
import re
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, Field, field_validator, model_validator

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

STACK_DIR = Path(__file__).resolve().parent / "stack"
PROD_COMPOSE_FILE = STACK_DIR / "docker-compose.yaml"
IMAGE_LOCK_FILE = STACK_DIR / "images.json"

REGISTRY = "ghcr.io/plugin-healthcare/pluginlake"
IMAGE_NAMES = ("api", "dagster-webserver", "ui-central", "ui-datastation")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ImageLockError(ValueError):
    """The images lock is missing, malformed or does not match the installed package."""


def image_env_var(name: str) -> str:
    """Return the compose variable that holds the reference of image ``name``.

    Args:
        name: Image name, e.g. ``dagster-webserver``.

    Returns:
        The variable name, e.g. ``PLUGINLAKE_IMAGE_DAGSTER_WEBSERVER``.
    """
    return "PLUGINLAKE_IMAGE_" + name.upper().replace("-", "_")


def image_ref(name: str, version: str, digest: str) -> str:
    """Return the pinned reference ``<registry>/<name>:<version>@<digest>``.

    Args:
        name: Image name.
        version: Release version, used as the tag.
        digest: Manifest digest (``sha256:...``).

    Returns:
        The image reference; the tag is informative, the digest decides what runs.
    """
    return f"{REGISTRY}/{name}:{version}@{digest}"


class ImageLock(BaseModel):
    """Digest-pinned references of our images for one release."""

    version: str | None = Field(default=None, description="Release version the images belong to.")
    images: dict[str, str] = Field(default_factory=dict, description="Image name to pinned reference.")

    @field_validator("images")
    @classmethod
    def _pinned_refs(cls, images: dict[str, str]) -> dict[str, str]:
        for name, ref in images.items():
            if name not in IMAGE_NAMES:
                msg = f"unknown image '{name}' (expected one of {', '.join(IMAGE_NAMES)})."
                raise ValueError(msg)
            prefix = f"{REGISTRY}/{name}:"
            repo_tag, _, digest = ref.partition("@")
            if not repo_tag.startswith(prefix) or not _DIGEST.match(digest):
                msg = f"image '{name}' must be '{prefix}<version>@sha256:<digest>', got '{ref}'."
                raise ValueError(msg)
        return images

    @model_validator(mode="after")
    def _complete(self) -> "ImageLock":
        if self.images and set(self.images) != set(IMAGE_NAMES):
            missing = sorted(set(IMAGE_NAMES) - set(self.images))
            msg = f"images lock is incomplete, missing: {', '.join(missing)}."
            raise ValueError(msg)
        if self.images and not self.version:
            msg = "images lock has images but no version."
            raise ValueError(msg)
        return self

    @property
    def is_empty(self) -> bool:
        """Whether the lock holds no images (source checkout, unreleased build)."""
        return not self.images

    def compose_env(self) -> dict[str, str]:
        """Return the ``PLUGINLAKE_IMAGE_*`` variables for the production compose."""
        return {image_env_var(name): ref for name, ref in self.images.items()}


def load_image_lock(path: Path = IMAGE_LOCK_FILE) -> ImageLock:
    """Load and validate the images lock.

    Args:
        path: Path to ``images.json``.

    Returns:
        The validated lock; empty when the file is missing.

    Raises:
        ImageLockError: If the file is not valid JSON or not a valid lock.
    """
    if not path.is_file():
        return ImageLock()
    try:
        return ImageLock.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        msg = f"invalid images lock {path}: {exc}"
        raise ImageLockError(msg) from exc


def _same_version(left: str, right: str) -> bool:
    try:
        return Version(left) == Version(right)
    except InvalidVersion:
        return left == right


def released_image_env(path: Path = IMAGE_LOCK_FILE) -> dict[str, str]:
    """Return the image variables of the installed release.

    Args:
        path: Path to ``images.json``.

    Returns:
        The ``PLUGINLAKE_IMAGE_*`` variables, all pinned by digest.

    Raises:
        ImageLockError: If the lock is empty, invalid, or belongs to another version
            than the installed pluginlake package.
    """
    lock = load_image_lock(path)
    if lock.is_empty:
        msg = (
            "this pluginlake build has no released images (empty images lock). Install a released "
            "version (pip install pluginlake) or run the dev stack from a checkout with 'pluginlake up --dev'."
        )
        raise ImageLockError(msg)
    try:
        installed = package_version("pluginlake")
    except PackageNotFoundError:
        installed = None
    if installed is not None and lock.version is not None and not _same_version(lock.version, installed):
        msg = f"images lock is for pluginlake {lock.version}, but {installed} is installed."
        raise ImageLockError(msg)
    return lock.compose_env()


def write_image_lock(version: str, digests: dict[str, str], path: Path = IMAGE_LOCK_FILE) -> ImageLock:
    """Write the images lock for a release.

    Args:
        version: Release version (without ``v``), also the image tag.
        digests: Image name to manifest digest, for every image in ``IMAGE_NAMES``.
        path: Destination file.

    Returns:
        The written lock.

    Raises:
        ImageLockError: If a digest is malformed or an image is missing.
    """
    bad = {name: digest for name, digest in digests.items() if not _DIGEST.match(digest)}
    if bad:
        msg = f"malformed digests: {bad}"
        raise ImageLockError(msg)
    try:
        lock = ImageLock(
            version=version,
            images={name: image_ref(name, version, digest) for name, digest in sorted(digests.items())},
        )
    except ValueError as exc:
        raise ImageLockError(str(exc)) from exc
    path.write_text(json.dumps(lock.model_dump(), indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote images lock for %s to %s", version, path)
    return lock


def _parse_digest(value: str) -> tuple[str, str]:
    name, sep, digest = value.partition("=")
    if not sep:
        msg = f"expected NAME=sha256:DIGEST, got '{value}'"
        raise argparse.ArgumentTypeError(msg)
    return name, digest


def main(argv: list[str] | None = None) -> int:
    """Write the images lock (release workflow).

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(prog="python -m pluginlake.deploy.images")
    subparsers = parser.add_subparsers(dest="command", required=True)
    write = subparsers.add_parser("write", help="Write stack/images.json for a release.")
    write.add_argument("--version", required=True, help="Release version without 'v', e.g. 0.2.0.")
    write.add_argument("--digest", action="append", type=_parse_digest, default=[], help="NAME=sha256:DIGEST")
    write.add_argument("--output", type=Path, default=IMAGE_LOCK_FILE, help="Destination (default: packaged lock).")
    args = parser.parse_args(argv)

    try:
        write_image_lock(args.version, dict(args.digest), args.output)
    except ImageLockError as exc:
        logger.error("%s", exc)  # noqa: TRY400 (expected input error, no traceback)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
