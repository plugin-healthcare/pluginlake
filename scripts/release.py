"""Release helpers for .github/workflows/release.yaml.

Commands:
    check-tag TAG     Validate a release tag against pyproject.toml. Writes
                      ``version`` and ``prerelease`` to $GITHUB_OUTPUT when set.
    notes VERSION     Print the CHANGELOG.md section of VERSION (release notes).

A tag is ``v`` plus the project version (``v0.2.0``, ``v0.2.0-rc.1``); a version
with a hyphen is a pre-release. Whether the tagged commit is on main is checked
in the workflow with git.
"""

import argparse
import os
import re
import sys
import tomllib
from pathlib import Path

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?)$")


class ReleaseError(ValueError):
    """The tag or changelog does not allow a release."""


def project_version(pyproject: Path = ROOT / "pyproject.toml") -> str:
    """Return ``project.version`` from pyproject.toml."""
    with pyproject.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def check_tag(tag: str, pyproject_version: str) -> tuple[str, bool]:
    """Validate ``tag`` against the project version.

    Args:
        tag: Git tag, e.g. ``v0.2.0-rc.1``.
        pyproject_version: ``project.version`` from pyproject.toml.

    Returns:
        The version without ``v`` and whether it is a pre-release.

    Raises:
        ReleaseError: If the tag is malformed or differs from the project version.
    """
    match = TAG_PATTERN.match(tag)
    if match is None:
        msg = f"tag '{tag}' is not 'v<major>.<minor>.<patch>[-<pre-release>]'."
        raise ReleaseError(msg)
    version = match.group("version")
    try:
        same = Version(version) == Version(pyproject_version)
    except InvalidVersion as exc:
        msg = f"tag '{tag}' is not a valid Python package version: {exc}"
        raise ReleaseError(msg) from exc
    if not same:
        msg = f"tag '{tag}' does not match version '{pyproject_version}' in pyproject.toml."
        raise ReleaseError(msg)
    return version, "-" in version


def release_notes(version: str, changelog: str) -> str:
    """Return the body of the ``## [version]`` section of a Keep a Changelog file.

    Raises:
        ReleaseError: If the section is missing or empty.
    """
    heading = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n", re.MULTILINE)
    match = heading.search(changelog)
    if match is None:
        msg = f"CHANGELOG.md has no '## [{version}]' section; move the Unreleased entries there first."
        raise ReleaseError(msg)
    rest = changelog[match.end() :]
    following = re.search(r"^## \[", rest, re.MULTILINE)
    body = (rest[: following.start()] if following else rest).strip()
    if not body:
        msg = f"CHANGELOG.md section '{version}' is empty."
        raise ReleaseError(msg)
    return body + "\n"


def _write_outputs(values: dict[str, str]) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with Path(output).open("a", encoding="utf-8") as handle:
        handle.writelines(f"{key}={value}\n" for key, value in values.items())


def main(argv: list[str] | None = None) -> int:
    """Run a release helper command and return the exit code."""
    parser = argparse.ArgumentParser(prog="scripts/release.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check-tag")
    check.add_argument("tag")
    notes = subparsers.add_parser("notes")
    notes.add_argument("version")
    args = parser.parse_args(argv)

    try:
        if args.command == "check-tag":
            version, prerelease = check_tag(args.tag, project_version())
            _write_outputs({"version": version, "prerelease": str(prerelease).lower()})
            sys.stdout.write(f"version={version} prerelease={str(prerelease).lower()}\n")
        else:
            sys.stdout.write(release_notes(args.version, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")))
    except ReleaseError as exc:
        sys.stderr.write(f"::error::{exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
