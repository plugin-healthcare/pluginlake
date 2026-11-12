"""Tests for the secret generator of the production compose."""

import stat
from pathlib import Path

import pytest
import yaml

from pluginlake.deploy.config import InitConfig, load_init_config
from pluginlake.deploy.init_secrets import build_secret_files, init_home


def _config(**overrides) -> InitConfig:
    data = {"folders": ["data"], "private_folders": [], "secrets_folder": "vault", "secrets": []} | overrides
    return InitConfig.model_validate(data)


def test_services_get_their_own_database_passwords():
    files = build_secret_files(load_init_config())
    passwords = [
        files[n] for n in ("postgres_password", "dagster_pg_password", "ducklake_pg_password", "zitadel_db_password")
    ]
    assert len(set(passwords)) == len(passwords)


def test_zitadel_config_file_holds_the_database_password():
    files = build_secret_files(load_init_config())
    config = yaml.safe_load(files["zitadel_config.yaml"])
    assert config["Database"]["Postgres"]["User"]["Password"] == files["zitadel_db_password"]


def test_zitadel_steps_file_holds_the_admin_password():
    files = build_secret_files(load_init_config())
    steps = yaml.safe_load(files["zitadel_steps.yaml"])
    assert steps["FirstInstance"]["Org"]["Human"]["Password"] == files["zitadel_admin_password"]


def test_zitadel_masterkey_is_32_characters():
    assert len(build_secret_files(load_init_config())["zitadel_masterkey"]) == 32


def test_init_home_creates_private_files_and_is_idempotent(tmp_path: Path):
    config = load_init_config()
    created = init_home(tmp_path, 1000, 1000, config)
    assert created
    assert all((tmp_path / f).is_dir() for f in [*config.folders, *config.private_folders, config.secrets_folder])
    assert stat.S_IMODE((tmp_path / "secrets" / "postgres_password").stat().st_mode) == 0o400
    assert "pluginlake:x:1000:1000" in (tmp_path / "passwd").read_text()

    before = (tmp_path / "secrets" / "postgres_password").read_text()
    assert init_home(tmp_path, 1000, 1000, config) == []
    assert (tmp_path / "secrets" / "postgres_password").read_text() == before


def test_init_home_creates_the_configured_folders_and_secrets(tmp_path: Path):
    config = _config(secrets=[{"name": "token", "kind": "hex", "services": []}])
    assert init_home(tmp_path, 1000, 1000, config) == ["token"]
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "vault" / "token").is_file()
    assert not (tmp_path / "postgres").exists()


def test_templates_follow_an_existing_secret(tmp_path: Path):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "zitadel_db_password").write_text("kept")
    init_home(tmp_path, 1000, 1000)
    config = yaml.safe_load((tmp_path / "secrets" / "zitadel_config.yaml").read_text())
    assert config["Database"]["Postgres"]["User"]["Password"] == "kept"  # noqa: S105


def test_a_template_must_refer_to_an_earlier_secret():
    secrets = [{"name": "a", "kind": "template", "template": "{b}", "services": []}]
    with pytest.raises(ValueError, match="declared before"):
        _config(secrets=secrets)


def test_template_is_required_for_template_secrets():
    with pytest.raises(ValueError, match="template"):
        _config(secrets=[{"name": "a", "kind": "template", "services": []}])
