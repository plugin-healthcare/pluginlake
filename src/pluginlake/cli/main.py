"""CLI entry point for pluginlake (``pluginlake ...``).

Only the standard library is imported here, so the missing-extra hint works
without ``typer`` and ``rich`` installed.
"""

import sys

INSTALL_HINT = 'The pluginlake CLI needs extra dependencies. Install them with: pip install "pluginlake[cli]"'


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code.
    """
    try:
        from pluginlake.cli.app import app  # noqa: PLC0415
    except ImportError:
        sys.stderr.write(f"{INSTALL_HINT}\n")
        return 1

    try:
        app(args=argv, prog_name="pluginlake")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
