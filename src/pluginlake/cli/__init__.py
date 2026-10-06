"""The ``pluginlake`` command-line interface.

Two responsibilities in this (focused) iteration, both owned by core so that
conforming is easier than not (ADR-009):

- ``pluginlake init <name>`` scaffolds a conformant project package.
- ``pluginlake verify [path]`` runs the conformance suite.
"""

from pluginlake.cli.main import main

__all__ = ["main"]
