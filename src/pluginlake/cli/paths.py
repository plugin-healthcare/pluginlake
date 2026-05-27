"""XDG-compliant path resolution for pluginlake instances."""

import os
from pathlib import Path


def xdg_config_home() -> Path:
    """Return XDG_CONFIG_HOME, defaulting to ~/.config."""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def xdg_data_home() -> Path:
    """Return XDG_DATA_HOME, defaulting to ~/.local/share."""
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def xdg_state_home() -> Path:
    """Return XDG_STATE_HOME, defaulting to ~/.local/state."""
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))


def instance_config_dir(instance_id: str) -> Path:
    """Return config directory for a given instance."""
    return xdg_config_home() / "pluginlake" / instance_id


def instance_data_dir(instance_id: str) -> Path:
    """Return data directory for a given instance."""
    return xdg_data_home() / "pluginlake" / instance_id


def instance_state_dir(instance_id: str) -> Path:
    """Return state directory for a given instance."""
    return xdg_state_home() / "pluginlake" / instance_id


def pluginlake_base_dir() -> Path:
    """Return the base pluginlake config directory (lists all instances)."""
    return xdg_config_home() / "pluginlake"


def list_instances() -> list[str]:
    """List all initialized instance IDs by scanning the config directory."""
    base = pluginlake_base_dir()
    if not base.exists():
        return []
    return sorted(d.name for d in base.iterdir() if d.is_dir() and (d / ".env").exists())
