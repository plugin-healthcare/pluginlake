"""Shared Rich consoles for CLI output."""

from rich.console import Console

_console = Console(highlight=False)
_err_console = Console(stderr=True, highlight=False)


def out(message: str = "") -> None:
    """Print a plain message to stdout."""
    _console.print(message, markup=False, soft_wrap=True)


def err(message: str) -> None:
    """Print a plain message to stderr."""
    _err_console.print(message, markup=False, soft_wrap=True)
