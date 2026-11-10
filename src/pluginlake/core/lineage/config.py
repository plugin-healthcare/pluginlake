"""OpenLineage settings for the Dagster lineage bridge (ADR-007)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LineageSettings(BaseSettings):
    """Settings for emitting OpenLineage events.

    ``url`` and ``job_namespace`` use the standard OpenLineage variables
    ``OPENLINEAGE_URL`` and ``OPENLINEAGE_NAMESPACE``; the other settings use the
    ``PLUGINLAKE_LINEAGE_`` prefix. Emission is off while ``url`` is unset. With
    ``lineage = true`` in ``pluginlake.toml``, ``pluginlake up`` sets the URL to
    ``http://marquez:5000`` and the namespace to the station's ``lineage_namespace``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_LINEAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    url: str | None = Field(
        default=None,
        validation_alias="OPENLINEAGE_URL",
        description="Base URL of the OpenLineage backend, e.g. Marquez.",
    )
    job_namespace: str = Field(
        default="pluginlake",
        validation_alias="OPENLINEAGE_NAMESPACE",
        description="OpenLineage namespace for Dagster asset jobs; one per node.",
    )
    endpoint: str = Field(default="api/v1/lineage", description="OpenLineage API path relative to `url`.")
    timeout: float = Field(default=5.0, description="HTTP timeout in seconds per request.")
    retries: int = Field(default=1, ge=0, description="HTTP retries per event on connection errors and 5xx responses.")
    dataset_namespace: str = Field(default="ducklake", description="OpenLineage namespace for DuckLake datasets.")

    @property
    def enabled(self) -> bool:
        """Whether an OpenLineage backend is configured."""
        return bool(self.url)
