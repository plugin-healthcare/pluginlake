"""OMOP module configuration."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from pluginlake.config import Settings as BaseSettings


class OMOPSettings(BaseSettings):
    """OMOP-specific configuration.

    Configuration for OMOP CDM data ingestion, validation, and storage.
    All paths are relative to the project root unless absolute.
    """

    model_config = SettingsConfigDict(
        env_prefix="OMOP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    raw_data_dir: Path = Field(
        default=Path("data/raw/omop"),
        description="Directory containing raw OMOP CSV files",
    )

    validate_on_load: bool = Field(
        default=True,
        description="Run schema validation during CSV loading",
    )
    validate_foreign_keys: bool = Field(
        default=False,
        description="Validate foreign key constraints (expensive)",
    )
    skip_invalid_rows: bool = Field(
        default=False,
        description="Skip invalid rows instead of failing",
    )

    batch_size: int = Field(
        default=100_000,
        description="Row batch size for processing",
    )
    csv_encoding: str = Field(
        default="utf-8",
        description="CSV file encoding",
    )
    infer_schema_length: int = Field(
        default=10_000,
        description="Number of rows to scan for CSV schema inference",
    )

    cdm_version: str = Field(
        default="5.4",
        description="OMOP CDM version to validate against",
    )

    vocabulary_dir: Path = Field(
        default=Path("data/omop_vocabularies"),
        description="Directory containing OMOP vocabulary files",
    )
    vocabulary_schema: str = Field(
        default="omop_vocab",
        description="DuckDB schema name for vocabulary tables",
    )
    vocabulary_auto_load: bool = Field(
        default=True,
        description="Automatically load vocabularies on first query",
    )
    validate_concepts: bool = Field(
        default=True,
        description="Validate concept IDs against vocabulary tables during ingestion",
    )

    folder_watch_interval: int = Field(
        default=30,
        description="Sensor polling interval in seconds for folder-based ingestion",
    )
    folder_watch_debounce_seconds: int = Field(
        default=60,
        description="Skip files modified within this many seconds to avoid duplicate triggers",
    )


def get_omop_settings() -> OMOPSettings:
    """Get OMOP module settings.

    Returns:
        Configured OMOPSettings instance.
    """
    return OMOPSettings()
