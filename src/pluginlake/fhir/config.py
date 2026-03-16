"""FHIR module configuration."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from pluginlake.config import Settings as BaseSettings


class FHIRSettings(BaseSettings):
    """FHIR-specific configuration.

    Configuration for FHIR NDJSON ingestion and FHIR-to-OMOP translation.
    All paths are relative to the project root unless absolute.
    """

    model_config = SettingsConfigDict(
        env_prefix="FHIR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    raw_data_dir: Path = Field(
        default=Path(".data/raw/fhir"),
        description="Directory containing raw FHIR NDJSON files",
    )

    folder_watch_interval: int = Field(
        default=30,
        description="Sensor polling interval in seconds for folder-based ingestion",
    )
    folder_watch_debounce_seconds: int = Field(
        default=60,
        description="Skip files modified within this many seconds to avoid duplicate triggers",
    )


def get_fhir_settings() -> FHIRSettings:
    """Get FHIR module settings.

    Returns:
        Configured FHIRSettings instance.
    """
    return FHIRSettings()
