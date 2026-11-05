"""Configuration for the DuckLake data catalog."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pluginlake.config import secrets_dir


class DuckLakeSettings(BaseSettings):
    """DuckLake catalog settings.

    All settings can be overridden via environment variables
    prefixed with ``DUCKLAKE_``. In compose the password is the Docker secret
    ``/run/secrets/ducklake_pg_password``.
    """

    model_config = SettingsConfigDict(
        env_prefix="DUCKLAKE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        secrets_dir=secrets_dir(),
    )

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
