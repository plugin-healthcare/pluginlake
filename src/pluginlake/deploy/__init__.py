"""Station deployment module.

Provides the operator-owned deployment surface (``pluginlake.toml``) and the
config-driven bring-up of the standardized stack. The station config declares
node settings and the project packages to deploy; core installs those projects
into the standardized images and discovery wires their code locations and
routers via the ``pluginlake.projects`` entry point (ADR-009).
"""
