"""Base class for pluggable storage backends."""

from abc import ABC, abstractmethod

import duckdb


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    Storage backends define where DuckLake stores its data files and
    how DuckDB connects to that storage. Implementations handle local
    filesystems, cloud object stores, and other storage systems.

    Each backend provides:
        - A base path for DuckLake file storage (DATA_PATH).
        - DuckDB extension configuration for accessing the storage.
    """

    @abstractmethod
    def get_base_path(self) -> str:
        """Return the root path for file storage.

        For local storage, this is a filesystem path.
        For cloud storage, this is a URI (e.g., ``s3://bucket/prefix/``).
        Used as DuckLake's DATA_PATH.
        """

    @abstractmethod
    def configure_duckdb(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Configure a DuckDB connection to access this storage.

        Install and load any required extensions, set credentials,
        and apply any other necessary configuration.

        Args:
            conn: An open DuckDB connection to configure.
        """
