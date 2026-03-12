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
        default="pluginlake Datastation",
        description="Browser tab title.",
    )
    page_icon: str = Field(
        default=":hospital:",
        description="Streamlit page icon.",
    )


def get_settings() -> DashboardSettings:
    """Return cached dashboard settings."""
    return DashboardSettings()
