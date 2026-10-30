"""Configuration for the ``pluginlake`` command-line interface."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CliSettings(BaseSettings):
    """Settings for the project scaffolding and demo commands.

    All settings can be overridden via environment variables
    prefixed with ``PLUGINLAKE_CLI_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGINLAKE_CLI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    template_package: str = Field(
        default="pluginlake.cli.templates", description="Package that holds the project template."
    )
    template_dir: str = Field(
        default="project", description="Directory of the project template inside the template package."
    )
    template_suffix: str = Field(default=".tmpl", description="Suffix that marks a file as a template to render.")
    demo_package: str = Field(
        default="pluginlake.demo", description="Package that holds the bundled demo station config."
    )
    demo_config_file: str = Field(
        default="pluginlake.demo.toml", description="File name of the bundled demo station config."
    )
    demo_workdir: Path = Field(
        default=Path(".pluginlake"), description="Directory for the demo config and demo project."
    )


@lru_cache
def get_cli_settings() -> CliSettings:
    """Return the cached CLI settings.

    Returns:
        The settings, read once from the environment.
    """
    return CliSettings()
