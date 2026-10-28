"""Typer application for the ``pluginlake`` command.

This module is the only place (with the command modules it imports) that needs
``typer`` and ``rich``, which are part of the base install.
"""

from pathlib import Path
from typing import Annotated

import typer

from pluginlake.cli.project import run_project_new
from pluginlake.cli.up import run_down, run_up
from pluginlake.cli.verify import run_verify

DEFAULT_CONFIG = Path("pluginlake.toml")

app = typer.Typer(
    name="pluginlake",
    help="Scaffold, verify, and deploy pluginlake data stations.",
    no_args_is_help=True,
    add_completion=True,
)
project_app = typer.Typer(help="Create and manage project packages.", no_args_is_help=True)
app.add_typer(project_app, name="project")

ConfigOption = Annotated[
    Path,
    typer.Option("--config", help="Path to the station config."),
]


def _exit(code: int) -> None:
    raise typer.Exit(code)


@project_app.command("new")
def project_new(
    name: Annotated[str, typer.Argument(help="Project name (lowercase, digits, hyphens; e.g. 'ehds-demo').")],
    dest: Annotated[Path, typer.Option(help="Directory to create the project package in.")] = Path(),
    *,
    force: Annotated[bool, typer.Option(help="Write into the target directory even if it already exists.")] = False,
) -> None:
    """Scaffold a new conformant project package."""
    _exit(run_project_new(name=name, dest=dest.resolve(), force=force))


@app.command()
def verify(
    project: Annotated[str | None, typer.Option(help="Only verify the project with this id.")] = None,
) -> None:
    """Run the conformance suite on installed projects."""
    _exit(run_verify(project=project))


@app.command()
def up(
    config: ConfigOption = DEFAULT_CONFIG,
    *,
    detach: Annotated[bool, typer.Option("--detach", "-d", help="Run containers in the background.")] = False,
    no_build: Annotated[bool, typer.Option("--no-build", help="Do not rebuild images before starting.")] = False,
) -> None:
    """Deploy the station stack with the configured projects."""
    _exit(run_up(config_path=config, detach=detach, build=not no_build))


@app.command()
def down(
    config: ConfigOption = DEFAULT_CONFIG,
    *,
    volumes: Annotated[bool, typer.Option("--volumes", "-v", help="Also remove named volumes.")] = False,
) -> None:
    """Stop the station stack."""
    _exit(run_down(config_path=config, volumes=volumes))
