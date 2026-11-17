"""CLI entry point for pluginlake (``pluginlake ...``)."""

import argparse
import sys
from pathlib import Path

from pluginlake.cli.init import run_init
from pluginlake.cli.secrets import run_secrets_get, run_secrets_list
from pluginlake.cli.up import run_down, run_up
from pluginlake.cli.verify import run_verify
from pluginlake.deploy.setup import run_setup
from pluginlake.utils.logger import setup_logging

_DEFAULT_CONFIG = Path("pluginlake.toml")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pluginlake",
        description="Scaffold, verify, and deploy pluginlake data stations.",
    )
    subparsers = parser.add_subparsers(dest="command")

    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument(
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help="Path to the station config (default: ./pluginlake.toml).",
    )

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

    up_parser = subparsers.add_parser(
        "up", parents=[config_parent], help="Deploy the station stack with the configured projects."
    )
    up_parser.add_argument("-d", "--detach", action="store_true", help="Run containers in the background.")
    up_parser.add_argument("--no-build", action="store_true", help="Do not rebuild images before starting.")

    setup_parser = subparsers.add_parser(
        "setup",
        parents=[config_parent],
        help="Prepare a production node: folders, secrets and compose.env (run before docker compose).",
    )
    setup_parser.add_argument("--home", type=Path, default=Path(".pluginlake"), help="Data folder (must exist).")
    setup_parser.add_argument(
        "--host-home", type=Path, default=None, help="The data folder as the Docker host sees it (inside a container)."
    )

    secrets_parser = subparsers.add_parser("secrets", help="List or read the secrets of a node.")
    secrets_parser.add_argument("--home", type=Path, default=Path(".pluginlake"), help="Data folder.")
    secrets_sub = secrets_parser.add_subparsers(dest="secrets_command", required=True)
    secrets_sub.add_parser("list", help="Show name, origin and presence of each secret, without values.")
    secrets_get = secrets_sub.add_parser("get", help="Print the value of one secret (needs read access to the file).")
    secrets_get.add_argument("name", help="Name of the secret.")

    down_parser = subparsers.add_parser("down", help="Stop the station stack (all profiles).")
    down_parser.add_argument("-v", "--volumes", action="store_true", help="Also remove named volumes.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "init": lambda: run_init(name=args.name, dest=args.dest, force=args.force),
        "verify": lambda: run_verify(project=args.project),
        "up": lambda: run_up(config_path=args.config, detach=args.detach, build=not args.no_build),
        "setup": lambda: run_setup(config_path=args.config, home=args.home, host_home=args.host_home),
        "secrets": lambda: (
            run_secrets_list(args.home) if args.secrets_command == "list" else run_secrets_get(args.home, args.name)
        ),
        "down": lambda: run_down(volumes=args.volumes),
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 0
    return handler()


if __name__ == "__main__":
    sys.exit(main())
