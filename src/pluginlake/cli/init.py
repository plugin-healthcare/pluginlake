"""``pluginlake init`` — scaffold a conformant project package.

Renders the bundled project template (``cli/templates/project``) into a new
package that passes ``pluginlake verify`` out of the box, so the golden path is
also the conformant path (ADR-009).
"""

import re
import sys
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from string import Template

from pluginlake.plugins.conformance import core_version
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

TEMPLATE_PACKAGE = "pluginlake.cli.templates"
TEMPLATE_DIR = "project"
TEMPLATE_SUFFIX = ".tmpl"
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def _core_requirement(installed: str) -> str:
    """Derive a conservative ``requires_core`` range from the installed core.

    Pins to the current minor series (``>=X.Y.0,<X.(Y+1).0``) so a scaffolded
    project declares compatibility with the core it was generated against.
    """
    parts = installed.split(".")
    major = parts[0] if parts and parts[0].isdigit() else "0"
    minor = parts[1] if len(parts) > 1 and parts[1].isdigit() else "0"
    return f">={major}.{minor}.0,<{major}.{int(minor) + 1}.0"


def _build_context(name: str) -> dict[str, str]:
    """Build the template substitution context from a project name."""
    package_name = name.replace("-", "_")
    class_prefix = "".join(part.capitalize() for part in name.split("-"))
    return {
        "project_id": name,
        "package_name": package_name,
        "catalog": package_name,
        "namespace": name,
        "config_prefix": f"{package_name.upper()}_",
        "class_prefix": class_prefix,
        "requires_core": _core_requirement(core_version()),
    }


def _iter_template_files(root: Traversable) -> "list[tuple[list[str], str]]":
    """Yield ``(relative path segments, text)`` for every template file."""
    collected: list[tuple[list[str], str]] = []

    def _walk(node: Traversable, prefix: list[str]) -> None:
        for child in node.iterdir():
            if child.is_dir():
                _walk(child, [*prefix, child.name])
            elif child.name.endswith(TEMPLATE_SUFFIX):
                collected.append(([*prefix, child.name], child.read_text(encoding="utf-8")))

    _walk(root, [])
    return collected


def _render_segment(segment: str, context: dict[str, str]) -> str:
    rendered = Template(segment).substitute(context)
    return rendered.removesuffix(TEMPLATE_SUFFIX)


def run_init(name: str, dest: Path, *, force: bool = False) -> int:
    """Scaffold a new project package.

    Args:
        name: Project name (lowercase, digits, hyphens; e.g. ``"ehds-demo"``).
        dest: Directory to create the project package in.
        force: Write into an existing target directory instead of failing.

    Returns:
        ``0`` on success, ``1`` on error.
    """
    if not _NAME_PATTERN.match(name):
        print(
            f"Invalid project name '{name}'. Use lowercase letters, digits, and hyphens, starting with a letter.",
            file=sys.stderr,
        )
        return 1

    target = dest / name
    if target.exists() and not force:
        print(f"Target '{target}' already exists. Use --force to write into it.", file=sys.stderr)
        return 1

    context = _build_context(name)
    template_root = resources.files(TEMPLATE_PACKAGE).joinpath(TEMPLATE_DIR)

    for segments, text in _iter_template_files(template_root):
        rel_parts = [_render_segment(seg, context) for seg in segments]
        out_path = target.joinpath(*rel_parts)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(Template(text).substitute(context), encoding="utf-8")
        logger.debug("Wrote %s", out_path)

    print(f"Created project '{name}' at {target}")
    print("\nNext steps:")
    print(f"  cd {target}")
    print("  uv sync")
    print("  uv run pluginlake verify")
    return 0
