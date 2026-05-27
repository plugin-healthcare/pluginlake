"""Init command: set up a new pluginlake deployment instance."""

import shutil
from importlib import resources as importlib_resources
from pathlib import Path

from pluginlake.cli.paths import list_instances
from pluginlake.cli.settings import DeploymentSettings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

TEMPLATES_PACKAGE = "pluginlake.cli.templates"


def _templates_dir() -> Path:
    """Resolve the path to bundled deploy templates."""
    ref = importlib_resources.files(TEMPLATES_PACKAGE)
    # For editable installs this is a Path directly
    return Path(str(ref))


def _prompt(label: str, default: str = "") -> str:
    """Prompt user for input with an optional default."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict."""
    env: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            env[key.strip()] = value.strip()
    return env


def run_init(env_file: Path | None = None) -> None:
    """Run the init command: prompt, generate, and write config.

    Args:
        env_file: Optional existing .env to pre-populate settings from.
    """
    print("pluginlake — deployment setup\n")

    # Pre-populate from existing env file
    existing: dict[str, str] = {}
    if env_file and env_file.exists():
        existing = _load_env_file(env_file)
        print(f"  Loaded existing config from: {env_file}\n")

    # Show existing instances
    instances = list_instances()
    if instances:
        print(f"  Existing instances: {', '.join(instances)}\n")

    # Prompt for required fields
    datastation_id = _prompt(
        "Datastation ID",
        existing.get("DATASTATION_ID", "ds-001"),
    )
    datastation_name = _prompt(
        "Datastation name",
        existing.get("DATASTATION_NAME", "My Datastation"),
    )

    # Build settings (auto-derives passwords, DB names, paths)
    password_kwargs = {}
    existing_pw = existing.get("POSTGRES_PASSWORD")
    if existing_pw:
        from pydantic import SecretStr

        password_kwargs["postgres_password"] = SecretStr(existing_pw)

    settings = DeploymentSettings(
        datastation_id=datastation_id,
        datastation_name=datastation_name,
        postgres_user=existing.get("POSTGRES_USER", "pluginlake"),
        **password_kwargs,
    )

    # Find free ports
    settings.find_free_ports()

    # Create directory structure
    _create_directories(settings)

    # Write .env
    env_path = settings.write_env_file()

    # Copy config templates
    _write_templates(settings)

    # Summary
    print("\n  Instance initialized successfully!\n")
    print(f"  Config:  {settings.config_dir}")
    print(f"  Data:    {settings.data_dir}")
    print(f"  State:   {settings.state_dir}")
    print(f"  Env:     {env_path}")
    print("\n  Ports:")
    print(f"    API:           {settings.server_port}")
    print(f"    Dagster UI:    {settings.dagster_port}")
    print(f"    Code server:   {settings.code_server_port}")
    print(f"    PostgreSQL:    {settings.postgres_port}")
    print("\n  Next steps:")
    print(f"    pluginlake up --instance {datastation_id}")
    print(f"    pluginlake up --instance {datastation_id} --profile ui")


def _create_directories(settings: DeploymentSettings) -> None:
    """Create the XDG directory structure for the instance."""
    dirs = [
        settings.config_dir,
        settings.data_dir / "storage",
        settings.state_dir / "dagster",
        settings.state_dir / "logs" / "compute",
        settings.state_dir / "logs" / "dagster",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        logger.debug("Created: %s", d)


def _write_templates(settings: DeploymentSettings) -> None:
    """Copy dagster.yaml and workspace.yaml templates into the config directory."""
    templates = _templates_dir()

    # dagster.yaml — substitute variables
    dagster_template = templates / "dagster.yaml"
    if dagster_template.exists():
        content = dagster_template.read_text()
        (settings.config_dir / "dagster.yaml").write_text(content)
    else:
        # Fallback: copy from project config
        project_dagster = Path(__file__).resolve().parents[3] / "config" / "dagster" / "dagster.yaml"
        if project_dagster.exists():
            shutil.copy2(project_dagster, settings.config_dir / "dagster.yaml")

    # workspace.yaml
    workspace_template = templates / "workspace.yaml"
    if workspace_template.exists():
        (settings.config_dir / "workspace.yaml").write_text(workspace_template.read_text())
    else:
        project_workspace = Path(__file__).resolve().parents[3] / "config" / "dagster" / "workspace.yaml"
        if project_workspace.exists():
            shutil.copy2(project_workspace, settings.config_dir / "workspace.yaml")
