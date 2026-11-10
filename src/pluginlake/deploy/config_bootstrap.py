"""Settings for the first-run bootstrap (``pluginlake-init``)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class BootstrapSettings(BaseSettings):
    """Settings for ``python -m pluginlake.deploy.bootstrap``.

    All settings can be overridden via environment variables prefixed with
    ``PLUGINLAKE_BOOTSTRAP_``.
    """

    model_config = SettingsConfigDict(env_prefix="PLUGINLAKE_BOOTSTRAP_", extra="ignore")

    domain: str = "pluginlake.localhost"
    protected_subdomains: list[str] = ["api", "dagster", "dashboard", "marquez", "prometheus"]
    zitadel_url: str = "http://zitadel-api:8080"
    admin_pat_file: Path = Path("/bootstrap/admin.pat")
    proxy_config_file: Path = Path("/bootstrap/oauth2-proxy.cfg")
    project_name: str = "pluginlake"
    app_name: str = "oauth2-proxy"
    wait_seconds: int = 180

    @property
    def auth_host(self) -> str:
        """Public hostname of the identity provider."""
        return f"auth.{self.domain}"

    @property
    def protected_hosts(self) -> list[str]:
        """Public hostnames that sit behind the forward-auth proxy."""
        return [f"{name}.{self.domain}" for name in self.protected_subdomains]
