"""Dagster code location definitions for pluginlake.

Provides the standard Definitions and exposes core_assets for reuse
by external repos that want to extend the default pipeline.

Usage (standalone):
    dagster dev -m pluginlake.definitions

Usage (extend in a custom repo):
    from pluginlake.definitions import core_assets
    defs = Definitions(assets=[*core_assets, my_custom_asset])
"""

from dagster import Definitions

# Core assets that ship with every data station.
# Add new core assets here as they are implemented.
core_assets: list = []

defs = Definitions(assets=core_assets)
