"""CLI entry point for pluginlake (``pluginlake ...``)."""

import argparse
import sys
from pathlib import Path

from pluginlake.cli.init import run_init
from pluginlake.cli.up import run_down, run_up
from pluginlake.cli.verify import run_verify

_DEFAULT_CONFIG = Path("pluginlake.toml")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pluginlake",
        description="Scaffold, verify, and deploy pluginlake data stations.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Scaffold a new conformant project package.")
    init_parser.add_argument("name", help="Project name (lowercase, digits, and hyphens; e.g. 'ehds-demo').")
    init_parser.add_argument(
        "--dest",
        type=Path,
        default=Path.cwd(),
        help="Directory to create the project package in (default: current directory).",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Write into the destination even if the target directory already exists.",
    )

    verify_parser = subparsers.add_parser("verify", help="Run the conformance suite on installed projects.")
    verify_parser.add_argument(
        "--project",
        default=None,
        help="Only verify the project with this id (default: all discovered projects).",
    )

    up_parser = subparsers.add_parser("up", help="Deploy the station stack with the configured projects.")
    up_parser.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help="Path to the station config (default: ./pluginlake.toml).",
    )
    up_parser.add_argument("-d", "--detach", action="store_true", help="Run containers in the background.")
    up_parser.add_argument("--no-build", action="store_true", help="Do not rebuild images before starting.")

    down_parser = subparsers.add_parser("down", help="Stop the station stack.")
    down_parser.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help="Path to the station config (default: ./pluginlake.toml).",
    )
    down_parser.add_argument("-v", "--volumes", action="store_true", help="Also remove named volumes.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "init":
        return run_init(name=args.name, dest=args.dest, force=args.force)

    if args.command == "verify":
        return run_verify(project=args.project)

    if args.command == "up":
        return run_up(config_path=args.config, detach=args.detach, build=not args.no_build)

    if args.command == "down":
        return run_down(config_path=args.config, volumes=args.volumes)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
