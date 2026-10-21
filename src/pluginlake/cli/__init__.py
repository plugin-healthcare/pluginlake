"""The ``pluginlake`` command-line interface.

Commands owned by core so that conforming is easier than not (ADR-009):

- ``pluginlake project new <name>`` scaffolds a conformant project package.
- ``pluginlake verify`` runs the conformance suite.
- ``pluginlake up`` and ``pluginlake down`` deploy and stop the station stack.

The CLI needs the ``pluginlake[cli]`` extra (Typer and Rich).
"""

from pluginlake.cli.main import main

__all__ = ["main"]
