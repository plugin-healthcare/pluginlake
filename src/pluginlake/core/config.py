"""Configuration for the DuckLake data catalog."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

from pluginlake.config import settings_config

# DuckDB size literal, e.g. "2GB", "512MB", "1.5GiB".
_SIZE_PATTERN = r"^\d+(\.\d+)?\s*(B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)$"


class DuckDBLimitSettings(BaseSettings):
    """Resource limits of every DuckDB connection pluginlake opens.

    Each connection is its own in-memory DuckDB instance, so the limits apply per
    connection (the API shares one; a Dagster run opens one per IO manager).
    A query that needs more memory than ``memory_limit`` spills to
    ``temp_directory``, up to ``max_temp_directory_size``; beyond that it fails
    with :class:`pluginlake.core.ducklake.setup.ResourceLimitError`.
    Environment variables are prefixed with ``DUCKLAKE_``.
    """

    model_config = settings_config("DUCKLAKE_")

    memory_limit: str = Field(default="2GB", pattern=_SIZE_PATTERN, description="Maximum memory per connection.")
    temp_directory: str = Field(
        default=".data/tmp/duckdb",
        pattern=r"^[^'\\]*$",
        description="Directory for spilling to disk, on the data volume in compose; empty disables spilling.",
    )
    max_temp_directory_size: str = Field(
        default="10GB", pattern=_SIZE_PATTERN, description="Maximum disk space a connection may spill to."
    )


class DuckLakeSettings(BaseSettings):
    """DuckLake catalog settings.

    All settings can be overridden via environment variables
    prefixed with ``DUCKLAKE_``. In compose the password is the Docker secret
    ``/run/secrets/ducklake_pg_password``.
    """

    model_config = settings_config("DUCKLAKE_", secrets=True)

    pg_host: str
    pg_port: int = 5432
    pg_user: str
    pg_password: SecretStr
    pg_db: str
    catalog_name: str = "lakehouse"
    data_path: str = ".data/lakehouse"

    target_file_size: int | None = None
    parquet_compression: str | None = None
    per_thread_output: bool | None = None

    @property
    def pg_connection_string(self) -> str:
        """Build the libpq connection string for DuckLake metadata."""
        return (
            f"host={self.pg_host} port={self.pg_port} "
            f"dbname={self.pg_db} user={self.pg_user} password={self.pg_password.get_secret_value()}"
        )

    @property
    def attach_url(self) -> str:
        """Build the full DuckLake ATTACH URL."""
        return f"ducklake:{self.pg_connection_string}"
