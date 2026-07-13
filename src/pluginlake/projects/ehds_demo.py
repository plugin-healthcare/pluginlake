"""EHDS demo project manifest (in-tree).

Registers the OMOP and FHIR code locations and API routers that currently live
in the core package as a single ``ehds-demo`` project. This proves the plugin
contract while the code is still in-tree; Phase 3 of the split moves this into
the standalone ``pluginlake-ehds-demo`` package unchanged.
"""

from pluginlake.plugins.manifest import CodeLocationSpec, ProjectManifest, RouterSpec

manifest = ProjectManifest(
    id="ehds-demo",
    catalog="ducklake",
    namespace="ehds-demo",
    config_prefix="EHDS_DEMO_",
    requires_core=">=0.1.0,<0.2.0",
    code_locations=[
        CodeLocationSpec(module="pluginlake.definitions.omop"),
        CodeLocationSpec(module="pluginlake.definitions.fhir"),
    ],
    routers=[
        RouterSpec(module="pluginlake.api.routers.omop"),
        RouterSpec(module="pluginlake.api.routers.omop_statistics"),
        RouterSpec(module="pluginlake.api.routers.fhir"),
        RouterSpec(module="pluginlake.api.routers.fhir_statistics"),
    ],
)
