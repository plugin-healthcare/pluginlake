"""DuckLake configuration using Pydantic Settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class DuckLakeSettings(BaseSettings):
    """Settings for the DuckLake data catalog.

    Controls the PostgreSQL connection used for DuckLake metadata and
    the storage path used for DuckLake data files (Parquet).

    All settings can be overridden via environment variables prefixed
    with ``PLUGINLAKE_DUCKLAKE_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_DUCKLAKE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_db: str

    data_path: str
    storage_backend: Literal["local"]

    @property
    def pg_connection_string(self) -> str:
        """Return the PostgreSQL connection string for DuckLake ATTACH."""
        return (
            f"host={self.pg_host} "
            f"port={self.pg_port} "
            f"user={self.pg_user} "
            f"password={self.pg_password} "
            f"dbname={self.pg_db}"
        )
