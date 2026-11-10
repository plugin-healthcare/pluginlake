"""Root settings for pluginlake.

Provides Pydantic Settings-based configuration with environment variable
support and a medallion-architecture storage layer structure:

All settings can be overridden via environment variables. See each class
for the applicable prefix.
"""

import logging
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, Field
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
# Docker secrets
# ---------------------------------------------------------------------------

SECRETS_DIR = Path("/run/secrets")


def secrets_dir() -> Path | None:
    """Directory pydantic reads secret files from, if present.

    Compose mounts secrets as ``/run/secrets/<env_prefix><field>`` (lowercase), so a
    settings class with ``settings_config(..., secrets=True)`` reads e.g. ``DUCKLAKE_PG_PASSWORD``
    from ``/run/secrets/ducklake_pg_password``. Environment variables take precedence.
    Returns ``None`` outside containers, where pydantic would warn about a missing directory.
    """
    return SECRETS_DIR if SECRETS_DIR.is_dir() else None


def settings_config(env_prefix: str = "", *, secrets: bool = False) -> SettingsConfigDict:
    """Return the ``model_config`` shared by all pluginlake settings classes.

    Settings read a ``.env`` file and ignore unknown keys, so one ``.env`` can
    serve every settings class.

    Args:
        env_prefix: Environment-variable prefix of the settings class.
        secrets: Also read fields from Docker secret files (see :func:`secrets_dir`).

    Returns:
        The settings config dict.
    """
    return SettingsConfigDict(
        env_prefix=env_prefix,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        secrets_dir=secrets_dir() if secrets else None,
    )


ResolvedPath = Annotated[Path, AfterValidator(Path.resolve)]
"""A path made absolute (relative to the working directory) on validation."""


# ---------------------------------------------------------------------------
# Base settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Base settings for pluginlake.

    All settings can be overridden via environment variables
    prefixed with ``PLUGINLAKE_``.
    """

    model_config = settings_config("PLUGINLAKE_")

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

    model_config = settings_config("PLUGINLAKE_STORAGE_")

    base_dir: ResolvedPath = Field(
        default=Path(".data"),
        validate_default=True,
        description="Root directory for all storage layers.",
    )
    backend: Literal["local"] = Field(
        default="local",
        description="Storage backend type. Currently only 'local' is supported.",
    )

    # -- Layer directory properties ------------------------------------------

    @property
    def raw_dir(self) -> Path:
        """Path to the raw (bronze) storage layer."""
        return self.get_layer_path(StorageLayer.RAW)

    @property
    def processed_dir(self) -> Path:
        """Path to the processed (silver) storage layer."""
        return self.get_layer_path(StorageLayer.PROCESSED)

    @property
    def output_dir(self) -> Path:
        """Path to the output (gold) storage layer."""
        return self.get_layer_path(StorageLayer.OUTPUT)

    # -- Helper methods ------------------------------------------------------

    def get_layer_path(self, layer: StorageLayer, *parts: str) -> Path:
        """Return a path within a specific storage layer.

        Args:
            layer: The storage layer to build the path in.
            *parts: Additional path segments appended after the layer directory.

        Returns:
            Absolute path combining base_dir, layer, and any extra segments.
        """
        return self.base_dir.joinpath(layer.value, *parts)

    def ensure_directories(self) -> None:
        """Create the base directory and all layer subdirectories.

        Raises:
            OSError: If directory creation fails due to permissions or
                other filesystem errors.
        """
        for path in self.layer_dirs.values():
            path.mkdir(parents=True, exist_ok=True)

    @property
    def layer_dirs(self) -> dict[StorageLayer, Path]:
        """Return a mapping of each storage layer to its directory path."""
        return {layer: self.get_layer_path(layer) for layer in StorageLayer}


# ---------------------------------------------------------------------------
# Server settings
# ---------------------------------------------------------------------------


class ServerSettings(BaseSettings):
    """HTTP server configuration.

    Environment variables are prefixed with ``PLUGINLAKE_SERVER_``.
    """

    model_config = settings_config("PLUGINLAKE_SERVER_")

    host: str = Field(default="0.0.0.0", description="Bind address for the HTTP server.")  # noqa: S104
    port: int = Field(default=8000, description="Port for the HTTP server.")


# ---------------------------------------------------------------------------
# Log settings
# ---------------------------------------------------------------------------


class LogSettings(BaseSettings):
    """Operational JSONL log configuration.

    Environment variables are prefixed with ``PLUGINLAKE_LOG_``.
    """

    model_config = settings_config("PLUGINLAKE_LOG_")

    base_dir: ResolvedPath = Field(
        default=Path(".data/logs"),
        validate_default=True,
        description="Root directory for operational JSONL logs.",
    )

    @property
    def query_log_dir(self) -> Path:
        """Path to the query/traffic log directory."""
        return self.base_dir / "query_log"

    @property
    def ingestion_log_dir(self) -> Path:
        """Path to the ingestion history log directory."""
        return self.base_dir / "ingestion_log"

    def ensure_directories(self) -> None:
        """Create both log subdirectories."""
        self.query_log_dir.mkdir(parents=True, exist_ok=True)
        self.ingestion_log_dir.mkdir(parents=True, exist_ok=True)
