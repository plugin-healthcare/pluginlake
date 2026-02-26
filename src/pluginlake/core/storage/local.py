"""Local filesystem storage backend."""

from pathlib import Path

import duckdb

from pluginlake.core.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Storage backend that uses the local filesystem.

    Args:
        base_path: Root directory for file storage.
            Created automatically if it does not exist.
    """

    def __init__(self, base_path: str | Path) -> None:
        """Initialise with the root directory for file storage."""
        self._base_path = Path(base_path).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)

    def get_base_path(self) -> str:
        """Return the absolute path to the storage root directory."""
        return str(self._base_path)

    def configure_duckdb(self, conn: duckdb.DuckDBPyConnection) -> None:
        """No extra configuration needed for local filesystem access."""
