"""The project plugin manifest.

The ``ProjectManifest`` is the single registration surface for a project
(ADR-009). It is deliberately declarative: core validates it and mounts the
project's contributions uniformly, so no arbitrary project code runs in the
gateway. The model is intentionally small for now and will grow (connectors,
predefined queries, UI page specs) as later phases land, without breaking
existing projects.
"""

from pydantic import BaseModel, Field


class CodeLocationSpec(BaseModel):
    """A Dagster code location contributed by a project.

    Attributes:
        module: Import path to the module exposing a ``Definitions`` object.
        attribute: Name of the ``Definitions`` attribute in that module.
    """

    module: str
    attribute: str = "defs"


class RouterSpec(BaseModel):
    """A FastAPI router contributed by a project.

    Attributes:
        module: Import path to the module exposing an ``APIRouter`` object.
        attribute: Name of the ``APIRouter`` attribute in that module.
    """

    module: str
    attribute: str = "router"


class ProjectManifest(BaseModel):
    """Declarative description of what a project contributes to a node.

    A project package exposes exactly one manifest through the
    ``pluginlake.projects`` entry point. Core discovers it and wires the
    declared code locations and routers uniformly (ADR-009).

    Attributes:
        id: Stable project identifier, used across naming conventions and
            asset URNs. Lowercase, digits and hyphens only.
        catalog: DuckLake catalog the project owns (one catalog per project).
        namespace: Asset-URN namespace for the project's datasets.
        config_prefix: Environment-variable prefix for the project's settings.
        requires_core: Version specifier for the core versions this project
            supports (for example ``">=0.1.0,<0.2.0"``).
        code_locations: Dagster code locations the project contributes.
        routers: API routers the project contributes.
    """

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    catalog: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    namespace: str
    config_prefix: str
    requires_core: str = ""
    code_locations: list[CodeLocationSpec] = Field(default_factory=list)
    routers: list[RouterSpec] = Field(default_factory=list)
