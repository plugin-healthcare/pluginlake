"""Tests for the role specification parser of pluginlake-db-init."""

from pathlib import Path

import pytest

from pluginlake.deploy.init_databases import RoleSpec, parse_role


def test_parse_role_reads_the_password_file(tmp_path: Path):
    password = tmp_path / "pw"
    password.write_text("s3cret\n")
    assert parse_role(f"zitadel:zitadel:{password}") == RoleSpec("zitadel", "zitadel", "s3cret")


def test_parse_role_without_database_is_a_monitoring_role(tmp_path: Path):
    password = tmp_path / "pw"
    password.write_text("x")
    assert parse_role(f"monitoring::{password}").database == ""


@pytest.mark.parametrize("spec", ["only-user", "a:b", ":db:/tmp/pw"])
def test_parse_role_rejects_malformed_specs(spec: str):
    with pytest.raises(ValueError, match="user:database:password_file"):
        parse_role(spec)
