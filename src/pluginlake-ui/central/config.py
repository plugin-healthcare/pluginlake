"""Configuration for the central dashboard."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CentralSettings(BaseSettings):
    """Central dashboard settings.

    All settings can be overridden via environment variables
    prefixed with ``DASHBOARD_CENTRAL_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="DASHBOARD_CENTRAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    station_urls: list[str] = Field(
        default=[],
        description=(
            "Comma-separated list of datastation API base URLs. "
            "Example: https://ds-a.example.com:8000,https://ds-b.example.com:8000"
        ),
    )
    station_timeout: float = Field(
        default=30.0,
        description="HTTP request timeout per station in seconds.",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for authenticating with datastations.",
    )
    page_title: str = Field(
        default="pluginlake Central",
        description="Browser tab title.",
    )
    page_icon: str = Field(
        default=":hospital:",
        description="Streamlit page icon.",
    )


def get_settings() -> CentralSettings:
    """Return cached central settings."""
    return CentralSettings()
