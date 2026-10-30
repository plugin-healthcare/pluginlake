"""``pluginlake project new`` — scaffold a conformant project package.

Renders the bundled project template (``cli/templates/project``) into a new
package that passes ``pluginlake verify`` out of the box, so the golden path is
also the conformant path (ADR-009).
"""

import re
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from string import Template

from pluginlake.cli.config import get_cli_settings
from pluginlake.cli.console import err, out
from pluginlake.cli.up import run_up
from pluginlake.deploy.config import load_station_config
from pluginlake.plugins.conformance import core_version
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def _core_requirement(installed: str) -> str:
    """Derive a conservative ``requires_core`` range from the installed core.

    Pins to the current minor series (``>=X.Y.0,<X.(Y+1).0``) so a scaffolded
    project declares compatibility with the core it was generated against.

    Args:
        installed: The installed core version, for example ``"0.1.0"``.

    Returns:
        The version range, for example ``">=0.1.0,<0.2.0"``.
    """
    parts = installed.split(".")
    major = parts[0] if parts and parts[0].isdigit() else "0"
    minor = parts[1] if len(parts) > 1 and parts[1].isdigit() else "0"
    return f">={major}.{minor}.0,<{major}.{int(minor) + 1}.0"


def default_catalog(name: str) -> str:
    """Derive the default catalog name (the Python package name) from a project name.

    Args:
        name: The project name (lowercase, digits, hyphens).

    Returns:
        The project name with hyphens replaced by underscores.
    """
    return name.replace("-", "_")


def _build_context(name: str, catalog: str | None) -> dict[str, str]:
    """Build the template substitution context from a project name.

    Args:
        name: The project name (lowercase, digits, hyphens).
        catalog: The catalog name, or ``None`` for the default.

    Returns:
        The placeholder values for the project templates.
    """
    package_name = default_catalog(name)
    class_prefix = "".join(part.capitalize() for part in name.split("-"))
    return {
        "project_id": name,
        "package_name": package_name,
        "catalog": catalog or package_name,
        "namespace": name,
        "config_prefix": f"{package_name.upper()}_",
        "class_prefix": class_prefix,
        "requires_core": _core_requirement(core_version()),
    }


def _iter_template_files(root: Traversable) -> "list[tuple[list[str], str]]":
    """Collect every template file below ``root``.

    Args:
        root: The template directory to walk.

    Returns:
        A ``(relative path segments, text)`` pair for each template file.
    """
    collected: list[tuple[list[str], str]] = []

    def _walk(node: Traversable, prefix: list[str]) -> None:
        for child in node.iterdir():
            if child.is_dir():
                _walk(child, [*prefix, child.name])
            elif child.name.endswith(get_cli_settings().template_suffix):
                collected.append(([*prefix, child.name], child.read_text(encoding="utf-8")))

    _walk(root, [])
    return collected


def _render_segment(segment: str, context: dict[str, str]) -> str:
    rendered = Template(segment).substitute(context)
    return rendered.removesuffix(get_cli_settings().template_suffix)


def run_project_new(name: str, dest: Path, *, catalog: str | None = None, force: bool = False) -> int:
    """Scaffold a new project package.

    Args:
        name: Project name (lowercase, digits, hyphens; e.g. ``"ehds-demo"``).
        dest: Directory to create the project package in.
        catalog: DuckLake catalog name. Defaults to the package name.
        force: Write into an existing target directory instead of failing.

    Returns:
        ``0`` on success, ``1`` on error.
    """
    if not _NAME_PATTERN.match(name):
        err(f"Invalid project name '{name}'. Use lowercase letters, digits, and hyphens, starting with a letter.")
        return 1

    target = dest / name
    if target.exists() and not force:
        err(f"Target '{target}' already exists. Use --force to write into it.")
        return 1

    settings = get_cli_settings()
    context = _build_context(name, catalog)
    template_root = resources.files(settings.template_package).joinpath(settings.template_dir)

    for segments, text in _iter_template_files(template_root):
        rel_parts = [_render_segment(seg, context) for seg in segments]
        out_path = target.joinpath(*rel_parts)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(Template(text).substitute(context), encoding="utf-8")
        logger.debug("Wrote %s", out_path)

    out(f"Created project '{name}' at {target}")
    out("\nNext steps:")
    out(f"  cd {target}")
    out("  uv sync")
    out("  uv run pytest")
    return 0


def run_project_demo(*, attach: bool = False, build: bool = True, workdir: Path | None = None) -> int:
    """Scaffold the demo project and start the stack with it.

    The bundled demo config is a prefilled ``pluginlake.toml``. It is copied into
    ``workdir`` and every local project it lists is generated from the project
    template at its configured path, so the demo is a real conformant project package.
    Existing projects are reused.

    Args:
        attach: Follow the logs after the stack is up.
        build: Rebuild images before starting.
        workdir: Directory that holds the demo config and projects. Defaults to the setting.

    Returns:
        Process exit code.
    """
    settings = get_cli_settings()
    workdir = workdir or settings.demo_workdir
    workdir.mkdir(parents=True, exist_ok=True)
    config_path = workdir / settings.demo_config_file
    template = resources.files(settings.demo_package).joinpath(settings.demo_config_file)
    config_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    for project in load_station_config(config_path).local_projects:
        target = (workdir / project.path).resolve()  # type: ignore[operator]
        if target.exists():
            continue
        if target.name != project.name:
            err(f"Demo project '{project.name}' must be at a path ending in '{project.name}', not '{project.path}'.")
            return 1
        code = run_project_new(name=project.name, dest=target.parent)
        if code != 0:
            return code
    return run_up(config_path, attach=attach, build=build)
