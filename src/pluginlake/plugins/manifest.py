"""The project plugin manifest.

The ``ProjectManifest`` is the single registration surface for a project
(ADR-009). It is deliberately declarative: core validates it and mounts the
project's contributions uniformly, so no arbitrary project code runs in the
gateway. The model stays small and grows additively (connectors, predefined
queries, UI page specs) as later phases land, without breaking existing
projects.
"""

from importlib import import_module
from typing import Any

from pydantic import BaseModel, Field


class ImportSpec(BaseModel):
    """A reference to an attribute in an importable module.

    Attributes:
        module: Import path to the module exposing the attribute.
        attribute: Name of the attribute to load from that module.
    """

    module: str
    attribute: str

    def load(self) -> Any:  # noqa: ANN401 - returns the referenced object, type varies by spec
        """Import the module and return the referenced attribute.

        Returns:
            The attribute referenced by this spec.

        Raises:
            ModuleNotFoundError: If the module cannot be imported.
            AttributeError: If the attribute does not exist on the module.
        """
        return getattr(import_module(self.module), self.attribute)


class CodeLocationSpec(ImportSpec):
    """A Dagster code location contributed by a project.

    ``attribute`` defaults to ``defs`` (the conventional ``Definitions`` name).
    """

    attribute: str = "defs"


class RouterSpec(ImportSpec):
    """A FastAPI router contributed by a project.

    ``attribute`` defaults to ``router`` (the conventional ``APIRouter`` name).
    """

    attribute: str = "router"


class ConnectorSpec(ImportSpec):
    """A data connector contributed by a project.

    Must resolve to a :class:`pluginlake.plugins.base.Connector` subclass.
    """


class SettingsSpec(ImportSpec):
    """The project's Pydantic Settings class.

    Must resolve to a :class:`pluginlake.plugins.base.ProjectSettings` subclass.
    ``attribute`` defaults to ``Settings``.
    """

    attribute: str = "Settings"


class ProjectManifest(BaseModel):
    """Declarative description of what a project contributes to a node.

    A project package exposes exactly one manifest through the
    ``pluginlake.projects`` entry point. Core discovers it and wires the
    declared code locations and routers uniformly (ADR-009). The conformance
    suite (:mod:`pluginlake.plugins.conformance`) validates the manifest before
    a project is allowed to load.

    Attributes:
        id: Stable project identifier, used across naming conventions and
            asset URNs. Lowercase, digits and hyphens only.
        catalog: DuckLake catalog the project owns (one catalog per project).
        namespace: Asset-URN namespace for the project's datasets.
        config_prefix: Environment-variable prefix for the project's settings.
        requires_core: PEP 440 specifier for the core versions this project
            supports (for example ``">=0.1.0,<0.2.0"``).
        code_locations: Dagster code locations the project contributes.
        routers: API routers the project contributes.
        connectors: Data connectors the project ships.
        settings: The project's Settings class, if any.
    """

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    catalog: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    namespace: str = Field(min_length=1)
    config_prefix: str = Field(min_length=1)
    requires_core: str = ""
    code_locations: list[CodeLocationSpec] = Field(default_factory=list)
    routers: list[RouterSpec] = Field(default_factory=list)
    connectors: list[ConnectorSpec] = Field(default_factory=list)
    settings: SettingsSpec | None = None
