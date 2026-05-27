"""CLI entry point for pluginlake deployment management."""

import argparse
import sys
from pathlib import Path

from pluginlake.cli.paths import list_instances


def _default_instance() -> str | None:
    """Return the default instance ID (first one found, or None)."""
    instances = list_instances()
    return instances[0] if len(instances) == 1 else None


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="pluginlake",
        description="Manage pluginlake datastation deployments.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- init ---
    init_parser = subparsers.add_parser("init", help="Initialize a new datastation instance.")
    init_parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Existing .env file to pre-populate settings from.",
    )

    # --- up ---
    up_parser = subparsers.add_parser("up", help="Start the deployment stack.")
    up_parser.add_argument("--instance", "-i", default=None, help="Instance ID (auto-detected if only one exists).")
    up_parser.add_argument("--profile", "-p", default=None, help="Compose profile to activate (e.g. 'ui').")
    up_parser.add_argument("--no-build", action="store_true", help="Skip image builds.")

    # --- down ---
    down_parser = subparsers.add_parser("down", help="Stop the deployment stack.")
    down_parser.add_argument("--instance", "-i", default=None, help="Instance ID.")
    down_parser.add_argument("--volumes", "-v", action="store_true", help="Also remove volumes.")

    # --- status ---
    status_parser = subparsers.add_parser("status", help="Show container health.")
    status_parser.add_argument("--instance", "-i", default=None, help="Instance ID.")

    # --- list ---
    subparsers.add_parser("list", help="List all initialized instances.")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "init":
        from pluginlake.cli.init import run_init

        run_init(env_file=args.env_file)

    elif args.command == "list":
        from pluginlake.cli.compose import run_list

        run_list()

    elif args.command in ("up", "down", "status"):
        instance_id = getattr(args, "instance", None) or _default_instance()
        if not instance_id:
            instances = list_instances()
            if not instances:
                print("No instances found. Run: pluginlake init", file=sys.stderr)
                sys.exit(1)
            print(
                f"Multiple instances found: {', '.join(instances)}\nUse --instance <id> to specify which one.",
                file=sys.stderr,
            )
            sys.exit(1)

        from pluginlake.cli.compose import run_down, run_status, run_up

        if args.command == "up":
            rc = run_up(instance_id, profile=args.profile, build=not args.no_build)
            sys.exit(rc)
        elif args.command == "down":
            rc = run_down(instance_id, volumes=args.volumes)
            sys.exit(rc)
        elif args.command == "status":
            rc = run_status(instance_id)
            sys.exit(rc)


if __name__ == "__main__":
    main()
