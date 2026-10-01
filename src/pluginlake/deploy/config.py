"""Station deployment configuration (``pluginlake.toml``).

The station config is the operator-owned deployment surface. It declares node
settings and the project packages to deploy on this data station. Each project
is either a local ``path`` (dev: mounted into the standardized images and
editable-installed) or a ``source`` (a ``uv pip install`` spec such as a PyPI
requirement or ``git+URL@rev``). Core installs the listed projects at container
start; discovery then wires their code locations and routers via the
``pluginlake.projects`` entry point (ADR-009), so no files are copied by hand.

Example ``pluginlake.toml``::

    [station]
    endpoint_url = "https://ds1.example.org"

    [[projects]]
    name = "ehds-demo"
    path = "../pluginlake-ehds-demo"  # dev: local checkout

    [[projects]]
    name = "other"
    source = "pluginlake-other @ git+https://github.com/org/other@v1.0.0"  # prod
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

# Where local project checkouts are mounted inside the standardized images.
CONTAINER_PROJECTS_DIR = "/opt/projects"


class ProjectSpec(BaseModel):
    """A single project to deploy on the station.

    Exactly one of ``path`` (local checkout, dev) or ``source`` (a pip/uv
    install spec, e.g. PyPI or ``git+URL@rev``) must be set.
    """

    name: str = Field(description="Human-readable project name; also the mounted checkout directory name.")
    path: Path | None = Field(default=None, description="Local checkout path (dev), relative to the config file.")
    source: str | None = Field(default=None, description="A `uv pip install` spec (PyPI requirement or git+URL@rev).")

    @model_validator(mode="after")
    def _exactly_one_origin(self) -> "ProjectSpec":
        if (self.path is None) == (self.source is None):
            msg = f"project '{self.name}': set exactly one of 'path' or 'source'."
            raise ValueError(msg)
        return self

    @property
    def is_local(self) -> bool:
        """Whether this project is a local checkout (``path``) rather than a pinned source."""
        return self.path is not None

    def install_spec(self) -> str:
        """Return the ``uv pip install`` argument for this project (as seen in-container)."""
        if self.path is not None:
            return f"-e {CONTAINER_PROJECTS_DIR}/{self.path.name}"
        return self.source  # type: ignore[return-value]


class StationSettings(BaseModel):
    """Node-level settings for the data station."""

    endpoint_url: str = Field(default="http://localhost:8000", description="Public endpoint URL of the station API.")
    dashboards: bool = Field(default=True, description="Whether to start the datastation dashboard UI.")


class StationConfig(BaseModel):
    """Parsed ``pluginlake.toml`` station configuration."""

    station: StationSettings = Field(default_factory=StationSettings)
    projects: list[ProjectSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> "StationConfig":
        names = [p.name for p in self.projects]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            msg = f"duplicate project names in station config: {sorted(duplicates)}."
            raise ValueError(msg)
        return self

    @property
    def local_projects(self) -> list[ProjectSpec]:
        """The projects deployed from a local checkout (``path``)."""
        return [p for p in self.projects if p.is_local]

    def projects_env(self) -> str:
        """Return the space-joined install specs for ``$PLUGINLAKE_PROJECTS``."""
        return " ".join(p.install_spec() for p in self.projects)


def load_station_config(path: Path) -> StationConfig:
    """Load and validate a ``pluginlake.toml`` station config.

    Args:
        path: Path to the ``pluginlake.toml`` file.

    Returns:
        The parsed and validated station configuration.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    if not path.exists():
        msg = f"Station config not found: {path}"
        raise FileNotFoundError(msg)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return StationConfig.model_validate(data)
