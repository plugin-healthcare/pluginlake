"""Settings for the first-run bootstrap (``pluginlake-init``)."""

from datetime import timedelta
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class BootstrapSettings(BaseSettings):
    """Settings for ``python -m pluginlake.deploy.bootstrap``.

    All settings can be overridden via environment variables prefixed with
    ``PLUGINLAKE_BOOTSTRAP_``.
    """

    model_config = SettingsConfigDict(env_prefix="PLUGINLAKE_BOOTSTRAP_", extra="ignore")

    domain: str = "pluginlake.localhost"
    protected_subdomains: list[str] = ["api", "console", "dagster", "marquez", "prometheus"]
    zitadel_url: str = "http://zitadel-api:8080"
    admin_pat_file: Path = Path("/bootstrap/admin/admin.pat")
    admin_granted_file: Path = Path("/bootstrap/admin/admin-granted")
    proxy_config_file: Path = Path("/bootstrap/proxy/oauth2-proxy.cfg")
    admin_username: str = "admin"
    project_name: str = "pluginlake"
    app_name: str = "oauth2-proxy"
    groups_hook_url: str = "http://zitadel-groups-hook:8000/groups"
    groups_hook_key_file: Path = Path("/bootstrap/hook/groups-hook.key")
    project_id_file: Path = Path("/bootstrap/hook/project-id")
    wait_seconds: int = 180
    # Longest a sign-in lasts, also while the session is in use: Zitadel refuses to refresh it after this.
    session_max_age: timedelta = timedelta(hours=12)

    @property
    def auth_host(self) -> str:
        """Public hostname of the identity provider."""
        return f"auth.{self.domain}"

    @property
    def protected_hosts(self) -> list[str]:
        """Public hostnames that sit behind the forward-auth proxy."""
        return [self.domain, *(f"{name}.{self.domain}" for name in self.protected_subdomains)]
