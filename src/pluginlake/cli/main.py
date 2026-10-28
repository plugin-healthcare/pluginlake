"""CLI entry point for pluginlake (``pluginlake ...``)."""

import sys

from pluginlake.cli.app import app


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    try:
        app(args=argv, prog_name="pluginlake")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
