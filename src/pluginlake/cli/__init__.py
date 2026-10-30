"""The ``pluginlake`` command-line interface.

Commands owned by core so that conforming is easier than not (ADR-009):

- ``pluginlake project new`` scaffolds a conformant project package (asks for the basics without ``--name``).
- ``pluginlake project demo`` scaffolds a small demo project and starts the stack with it.
- ``pluginlake verify`` runs the conformance suite.
- ``pluginlake up`` and ``pluginlake down`` deploy and stop the station stack.
- ``pluginlake status`` and ``pluginlake logs`` inspect it.

The CLI is part of the base install (Typer and Rich).
"""

from pluginlake.cli.main import main

__all__ = ["main"]
