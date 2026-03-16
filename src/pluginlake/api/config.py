"""Configuration module for pluginlake API."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    """Settings for the data ingestion endpoint.

    Controls file upload limits and allowed file types.
    Environment variables are prefixed with ``PLUGINLAKE_INGEST_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_INGEST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_file_size_mb: int = Field(
        default=500,
        description="Maximum upload file size in megabytes.",
    )
    allowed_extensions: list[str] = Field(
        default=[".csv", ".json", ".parquet", ".ndjson", ".xlsx"],
        description="Allowed file extensions for upload.",
    )
    dagster_job_name: str = Field(
        default="ingest_raw_file_job",
        description="Default Dagster job name to trigger after ingestion.",
    )
    dagster_webserver_url: str = Field(
        default="http://localhost:3000",
        description="URL of the Dagster webserver (GraphQL API).",
    )

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024
