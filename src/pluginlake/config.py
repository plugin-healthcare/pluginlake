"""Root settings for pluginlake."""

import logging
from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(StrEnum):
    """Supported log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


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
