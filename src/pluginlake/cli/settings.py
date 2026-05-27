"""Deployment settings model for pluginlake instances."""

import os
import re
import secrets
import socket
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from pluginlake.cli.paths import instance_config_dir, instance_data_dir, instance_state_dir

_MAX_PORT = 65535
_INSTANCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _normalize_id(datastation_id: str) -> str:
    """Normalize an ID for use in database names (replace hyphens with underscores)."""
    return datastation_id.replace("-", "_")


def _find_free_port(start: int, exclude: set[int] | None = None) -> int:
    """Find the first available TCP port starting from `start`."""
    exclude = exclude or set()
    port = start
    while port < _MAX_PORT:
        if port in exclude:
            port += 1
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                port += 1
            else:
                return port
    msg = f"No free port found starting from {start}"
    raise RuntimeError(msg)


class DeploymentSettings(BaseModel):
    """All settings needed to deploy a pluginlake instance.

    Only `datastation_id` and `datastation_name` are required inputs.
    Everything else is auto-generated or derived.
    """

    datastation_id: str = Field(description="Unique identifier for this datastation, e.g. 'ds-cardiology-amc'.")
    datastation_name: str = Field(description="Human-readable name, e.g. 'AMC Cardiology'.")

    @field_validator("datastation_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _INSTANCE_ID_PATTERN.match(v):
            msg = "Must be lowercase alphanumeric with hyphens (e.g. 'ds-001')"
            raise ValueError(msg)
        return v

    postgres_user: str = Field(default="pluginlake", description="PostgreSQL superuser name.")
    postgres_password: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(32)),
        description="PostgreSQL password (auto-generated if not provided).",
    )
    postgres_port: int = Field(default=5432, description="Host port for PostgreSQL.")

    dagster_pg_db: str = Field(default="", description="Dagster database name (derived from ID).")
    dagster_port: int = Field(default=3000, description="Host port for Dagster webserver.")

    ducklake_pg_db: str = Field(default="", description="DuckLake database name (derived from ID).")

    server_port: int = Field(default=8000, description="Host port for pluginlake API.")

    code_server_port: int = Field(default=4000, description="Host port for Dagster code server.")

    uid: int = Field(default_factory=os.getuid, description="Host UID for container user mapping.")
    gid: int = Field(default_factory=os.getgid, description="Host GID for container user mapping.")

    config_dir: Path = Field(default=Path(), description="Instance config directory.")
    data_dir: Path = Field(default=Path(), description="Instance data directory.")
    state_dir: Path = Field(default=Path(), description="Instance state directory.")

    @model_validator(mode="after")
    def _derive_defaults(self) -> "DeploymentSettings":
        """Fill in derived values from datastation_id."""
        normalized = _normalize_id(self.datastation_id)

        if not self.dagster_pg_db:
            self.dagster_pg_db = f"dagster_{normalized}"

        if not self.ducklake_pg_db:
            self.ducklake_pg_db = f"ducklake_{normalized}"

        # Resolve paths
        self.config_dir = instance_config_dir(self.datastation_id)
        self.data_dir = instance_data_dir(self.datastation_id)
        self.state_dir = instance_state_dir(self.datastation_id)

        return self

    def find_free_ports(self) -> None:
        """Reassign ports to the first available ones (avoids conflicts)."""
        used: set[int] = set()

        self.postgres_port = _find_free_port(self.postgres_port, used)
        used.add(self.postgres_port)

        self.server_port = _find_free_port(self.server_port, used)
        used.add(self.server_port)

        self.dagster_port = _find_free_port(self.dagster_port, used)
        used.add(self.dagster_port)

        self.code_server_port = _find_free_port(self.code_server_port, used)
        used.add(self.code_server_port)

    def to_env_dict(self) -> dict[str, str]:
        """Serialize settings to a flat dict suitable for a .env file."""
        return {
            "DATASTATION_ID": self.datastation_id,
            "DATASTATION_NAME": self.datastation_name,
            "PUID": str(self.uid),
            "PGID": str(self.gid),
            "POSTGRES_USER": self.postgres_user,
            "POSTGRES_PASSWORD": self.postgres_password.get_secret_value(),
            "POSTGRES_PORT": str(self.postgres_port),
            "DAGSTER_PG_DB": self.dagster_pg_db,
            "DAGSTER_PG_USER": self.postgres_user,
            "DAGSTER_PG_PASSWORD": self.postgres_password.get_secret_value(),
            "DAGSTER_PORT": str(self.dagster_port),
            "DUCKLAKE_PG_DB": self.ducklake_pg_db,
            "DUCKLAKE_PG_USER": self.postgres_user,
            "DUCKLAKE_PG_PASSWORD": self.postgres_password.get_secret_value(),
            "PLUGINLAKE_SERVER_PORT": str(self.server_port),
            "CODE_SERVER_PORT": str(self.code_server_port),
            "PLUGINLAKE_CONFIG_DIR": str(self.config_dir),
            "PLUGINLAKE_DATA_DIR": str(self.data_dir),
            "PLUGINLAKE_STATE_DIR": str(self.state_dir),
        }

    def write_env_file(self, path: Path | None = None) -> Path:
        """Write settings as a .env file.

        Args:
            path: Target path. Defaults to config_dir/.env.

        Returns:
            The path where the .env file was written.
        """
        target = path or (self.config_dir / ".env")
        target.parent.mkdir(parents=True, exist_ok=True)

        lines = [f"{key}={value}" for key, value in self.to_env_dict().items()]
        target.write_text("\n".join(lines) + "\n")

        # Restrict permissions (contains secrets)
        target.chmod(0o600)
        return target
