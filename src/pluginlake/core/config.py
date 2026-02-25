"""Configuration for the DuckLake data catalog."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DuckLakeSettings(BaseSettings):
    """DuckLake catalog settings.

    All settings can be overridden via environment variables
    prefixed with ``DUCKLAKE_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="DUCKLAKE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    pg_host: str = Field(validation_alias="PG_HOST")
    pg_port: int = Field(default=5432, validation_alias="PG_PORT")
    pg_user: str = Field(validation_alias="PG_USER")
    pg_password: str = Field(validation_alias="PG_PASSWORD")
    pg_db: str = Field(validation_alias="PG_DB")
    catalog_name: str = Field(default="lakehouse", validation_alias="CATALOG_NAME")
    data_path: str = Field(default=".data/lakehouse", validation_alias="DATA_PATH")

    @property
    def pg_connection_string(self) -> str:
        """Build the libpq connection string for DuckLake metadata."""
        return (
            f"host={self.pg_host} port={self.pg_port} "
            f"dbname={self.pg_db} user={self.pg_user} password={self.pg_password}"
        )

    @property
    def attach_url(self) -> str:
        """Build the full DuckLake ATTACH URL."""
        return f"ducklake:{self.pg_connection_string}"
