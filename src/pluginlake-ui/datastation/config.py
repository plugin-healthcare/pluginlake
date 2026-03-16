"""Configuration for the datastation dashboard."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardSettings(BaseSettings):
    """Datastation dashboard settings.

    All settings can be overridden via environment variables
    prefixed with ``DASHBOARD_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="DASHBOARD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_url: str = Field(
        default="http://pluginlake:8000",
        description="Base URL of the local pluginlake FastAPI.",
    )
    api_timeout: float = Field(
        default=30.0,
        description="HTTP request timeout in seconds.",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for authenticating with pluginlake.",
    )
    page_title: str = Field(
        default="pluginlake",
        description="Browser tab title.",
    )
    page_icon: str = Field(
        default=":hospital:",
        description="Streamlit page icon.",
    )
    dagster_url: str = Field(
        default="http://localhost:3000/asset-groups",
        description="URL of the Dagster webserver UI.",
    )
    datastation_id: str = Field(
        default="ds-local-001",
        description="Unique identifier for this datastation.",
    )
    datastation_name: str = Field(
        default="demo-1",
        description="Human-readable name for this datastation.",
    )
    assets_dir: str = Field(
        default="/app/assets",
        description="Path to the shared assets directory (logos, images).",
    )


def get_settings() -> DashboardSettings:
    """Return cached dashboard settings."""
    return DashboardSettings()
