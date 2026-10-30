"""Typer application for the ``pluginlake`` command.

This module is the only place (with the command modules it imports) that needs
``typer`` and ``rich``, which are part of the base install.
"""

from pathlib import Path
from typing import Annotated

import typer

from pluginlake.cli.observe import run_logs, run_status
from pluginlake.cli.project import default_catalog, run_project_demo, run_project_new
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
    name: Annotated[str | None, typer.Option(help="Project name (lowercase, digits, hyphens; e.g. 'ehds-demo').")] = None,
    dest: Annotated[Path | None, typer.Option(help="Directory to create the project package in.")] = None,
    catalog: Annotated[str | None, typer.Option(help="DuckLake catalog name. Defaults to the package name.")] = None,
    *,
    force: Annotated[bool, typer.Option(help="Write into the target directory even if it already exists.")] = False,
) -> None:
    """Scaffold a new conformant project package.

    Without --name, asks for the name and the basic settings.
    """
    if name is None:
        name = typer.prompt("Project name (lowercase, digits, hyphens)")
        dest = Path(typer.prompt("Directory to create it in", default=".")) if dest is None else dest
        catalog = typer.prompt("Catalog name", default=default_catalog(name)) if catalog is None else catalog
    _exit(run_project_new(name=name, dest=(dest or Path()).resolve(), catalog=catalog, force=force))


@project_app.command("demo")
def project_demo(
    *,
    attach: Annotated[bool, typer.Option("--attach", help="Follow the logs after the stack is healthy.")] = False,
    no_build: Annotated[bool, typer.Option("--no-build", help="Do not rebuild images before starting.")] = False,
) -> None:
    """Start the stack with the bundled demo station config. Stop it with 'pluginlake down'."""
    _exit(run_project_demo(attach=attach, build=not no_build))


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
    attach: Annotated[bool, typer.Option("--attach", help="Follow the logs after the stack is healthy.")] = False,
    no_build: Annotated[bool, typer.Option("--no-build", help="Do not rebuild images before starting.")] = False,
) -> None:
    """Deploy the station stack and wait until it is healthy."""
    _exit(run_up(config_path=config, attach=attach, build=not no_build))


@app.command()
def down(config: ConfigOption = DEFAULT_CONFIG) -> None:
    """Stop the station stack. Volumes and data are never removed."""
    _exit(run_down(config_path=config))


@app.command()
def status(config: ConfigOption = DEFAULT_CONFIG) -> None:
    """Show whether each service is running and healthy (exit 1 if not)."""
    _exit(run_status(config_path=config))


@app.command()
def logs(
    service: Annotated[str | None, typer.Argument(help="Only show the logs of this service.")] = None,
    config: ConfigOption = DEFAULT_CONFIG,
    *,
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Keep streaming new log lines.")] = False,
) -> None:
    """Show the logs of the station stack."""
    _exit(run_logs(config_path=config, service=service, follow=follow))
