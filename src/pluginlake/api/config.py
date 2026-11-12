"""Configuration module for pluginlake API."""

from pydantic import Field
from pydantic_settings import BaseSettings

from pluginlake.config import settings_config


class IngestionSettings(BaseSettings):
    """Settings for the data ingestion endpoint.

    Controls file upload limits and allowed file types.
    Environment variables are prefixed with ``PLUGINLAKE_INGEST_``.
    """

    model_config = settings_config("PLUGINLAKE_INGEST_")

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


class MetricsSettings(BaseSettings):
    """Settings for the Prometheus ``/metrics`` endpoint.

    The endpoint is served on a separate port so it is never reachable through
    the public API port; compose binds it to ``0.0.0.0`` and only ``expose``s it
    on the internal network. Outside a container it defaults to loopback.
    Environment variables are prefixed with ``PLUGINLAKE_METRICS_``.
    """

    model_config = settings_config("PLUGINLAKE_METRICS_")

    enabled: bool = Field(default=True, description="Collect HTTP metrics and serve them on the metrics port.")
    host: str = Field(default="127.0.0.1", description="Bind address of the internal metrics server.")
    port: int = Field(default=9464, ge=1, le=65535, description="Port of the internal metrics server.")
