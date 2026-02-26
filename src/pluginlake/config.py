"""Root settings for pluginlake.

Provides Pydantic Settings-based configuration with environment variable
support and a medallion-architecture storage layer structure:

All settings can be overridden via environment variables. See each class
for the applicable prefix.
"""

import logging
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LogLevel(StrEnum):
    """Supported log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StorageLayer(StrEnum):
    """Storage layers following the medallion architecture.

    Attributes:
        RAW: Bronze layer — raw ingested data, stored as-is.
        PROCESSED: Silver layer — cleaned and transformed data.
        OUTPUT: Gold layer — curated, publication-ready datasets.
    """

    RAW = "raw"
    PROCESSED = "processed"
    OUTPUT = "output"


# ---------------------------------------------------------------------------
# Base settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Base settings for pluginlake.

    All settings can be overridden via environment variables
    prefixed with ``PLUGINLAKE_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    debug: bool = False
    log_level: LogLevel = LogLevel.INFO
    verbose: bool = False

    @property
    def effective_log_level(self) -> int:
        """Return the effective log level, accounting for verbose/debug flags."""
        if self.debug or self.verbose:
            return logging.DEBUG
        return logging.getLevelNamesMapping()[self.log_level.value]


# ---------------------------------------------------------------------------
# Storage settings
# ---------------------------------------------------------------------------


class StorageSettings(BaseSettings):
    """Storage layer configuration.

    Defines the base data directory and the medallion-architecture
    layer structure (raw / processed / output).

    Environment variables are prefixed with ``PLUGINLAKE_STORAGE_``.

    Examples:
        >>> settings = StorageSettings(base_dir="/tmp/data")
        >>> settings.raw_dir
        PosixPath('/tmp/data/raw')
        >>> settings.get_layer_path(StorageLayer.OUTPUT, "patients.parquet")
        PosixPath('/tmp/data/output/patients.parquet')
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_STORAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_dir: Path = Field(
        default=Path("data"),
        description="Root directory for all storage layers.",
    )
    backend: Literal["local"] = Field(
        default="local",
        description="Storage backend type. Currently only 'local' is supported.",
    )

    @model_validator(mode="after")
    def _resolve_base_dir(self) -> "StorageSettings":
        """Resolve relative base_dir to an absolute path."""
        self.base_dir = self.base_dir.resolve()
        return self

    # -- Layer directory properties ------------------------------------------

    @property
    def raw_dir(self) -> Path:
        """Path to the raw (bronze) storage layer."""
        return self.base_dir / StorageLayer.RAW

    @property
    def processed_dir(self) -> Path:
        """Path to the processed (silver) storage layer."""
        return self.base_dir / StorageLayer.PROCESSED

    @property
    def output_dir(self) -> Path:
        """Path to the output (gold) storage layer."""
        return self.base_dir / StorageLayer.OUTPUT

    # -- Helper methods ------------------------------------------------------

    def get_layer_path(self, layer: StorageLayer, *parts: str) -> Path:
        """Return a path within a specific storage layer.

        Args:
            layer: The storage layer to build the path in.
            *parts: Additional path segments appended after the layer directory.

        Returns:
            Absolute path combining base_dir, layer, and any extra segments.
        """
        return self.base_dir / layer.value / Path(*parts) if parts else self.base_dir / layer.value

    def ensure_directories(self) -> None:
        """Create the base directory and all layer subdirectories.

        Raises:
            OSError: If directory creation fails due to permissions or
                other filesystem errors.
        """
        for layer in StorageLayer:
            (self.base_dir / layer.value).mkdir(parents=True, exist_ok=True)

    @property
    def layer_dirs(self) -> dict[StorageLayer, Path]:
        """Return a mapping of each storage layer to its directory path."""
        return {layer: self.base_dir / layer.value for layer in StorageLayer}


# ---------------------------------------------------------------------------
# Server settings
# ---------------------------------------------------------------------------


class ServerSettings(BaseSettings):
    """HTTP server configuration.

    Environment variables are prefixed with ``PLUGINLAKE_SERVER_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_SERVER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", description="Bind address for the HTTP server.")  # noqa: S104
    port: int = Field(default=8000, description="Port for the HTTP server.")


# ---------------------------------------------------------------------------
# Postgres settings
# ---------------------------------------------------------------------------


class PostgresSettings(BaseSettings):
    """PostgreSQL connection configuration.

    Environment variables are prefixed with ``PLUGINLAKE_POSTGRES_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_POSTGRES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="localhost", description="PostgreSQL hostname.")
    port: int = Field(default=5432, description="PostgreSQL port.")
    user: SecretStr = Field(description="PostgreSQL user.")
    password: SecretStr = Field(description="PostgreSQL password.")
    db: str = Field(default="pluginlake", description="PostgreSQL database name.")


# ---------------------------------------------------------------------------
# Dagster settings
# ---------------------------------------------------------------------------


class DagsterSettings(BaseSettings):
    """Dagster orchestrator configuration.

    Environment variables are prefixed with ``PLUGINLAKE_DAGSTER_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_DAGSTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    module: str = Field(
        default="pluginlake.definitions",
        description="Python module containing Dagster definitions.",
    )
    webserver_url: str = Field(
        default="http://localhost:3000",
        description="URL of the Dagster webserver (GraphQL API).",
    )
    pg_host: str = Field(default="localhost", description="Dagster PostgreSQL hostname.")
    pg_user: SecretStr = Field(description="Dagster PostgreSQL user.")
    pg_password: SecretStr = Field(description="Dagster PostgreSQL password.")
    pg_db: str = Field(default="dagster", description="Dagster PostgreSQL database name.")
    DAGSTER_HOME: Path = Field(default=Path.home(), description="Directory for Dagster to store instance data.")
