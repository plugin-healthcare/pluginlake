"""Tests for the secret generator of the production compose."""

import stat
from pathlib import Path

from pluginlake.deploy.init_secrets import FOLDERS, build_secret_files, init_home, random_password


def test_random_password_meets_zitadel_policy():
    password = random_password()
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)
    assert any(c.isdigit() for c in password)
    assert any(not c.isalnum() for c in password)


def test_services_get_their_own_database_passwords():
    files = build_secret_files()
    passwords = [
        files[n] for n in ("postgres_password", "dagster_pg_password", "ducklake_pg_password", "zitadel_db_password")
    ]
    assert len(set(passwords)) == len(passwords)


def test_env_files_match_the_secret_files():
    files = build_secret_files()
    assert f"POSTGRES_PASSWORD={files['marquez_db_password']}" in files["marquez.env"]
    assert f"ZITADEL_DATABASE_POSTGRES_USER_PASSWORD={files['zitadel_db_password']}" in files["zitadel-api.env"]


def test_zitadel_masterkey_is_32_characters():
    assert len(build_secret_files()["zitadel_masterkey"]) == 32


def test_init_home_creates_private_files_and_is_idempotent(tmp_path: Path):
    created = init_home(tmp_path, 1000, 1000)
    assert created
    assert all((tmp_path / f).is_dir() for f in FOLDERS)
    assert stat.S_IMODE((tmp_path / "secrets" / "postgres_password").stat().st_mode) == 0o400
    assert "pluginlake:x:1000:1000" in (tmp_path / "passwd").read_text()

    before = (tmp_path / "secrets" / "postgres_password").read_text()
    assert init_home(tmp_path, 1000, 1000) == []
    assert (tmp_path / "secrets" / "postgres_password").read_text() == before
