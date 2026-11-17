"""Tests for the role specification parser of pluginlake-db-init."""

from pathlib import Path

import pytest

from pluginlake.deploy.init_databases import DatabaseOwnerError, RoleSpec, ensure_role, parse_role


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


class _Cursor:
    """Records the statements and answers the owner lookups."""

    def __init__(self, *, role_exists: bool, database_owner: str | None):
        self.role_exists = role_exists
        self.database_owner = database_owner
        self.statements: list[str] = []
        self._row: tuple | None = None

    def execute(self, query, params=None):  # noqa: ARG002
        text = query if isinstance(query, str) else repr(query)
        self.statements.append(text)
        if "FROM pg_roles" in text:
            self._row = (1,) if self.role_exists else None
        elif "FROM pg_database" in text:
            self._row = (self.database_owner,) if self.database_owner else None

    def fetchone(self):
        return self._row


def test_existing_roles_lose_elevated_attributes():
    cur = _Cursor(role_exists=True, database_owner="dagster")
    ensure_role(cur, RoleSpec("dagster", "dagster", "pw"))
    alter = next(s for s in cur.statements if "ALTER ROLE" in s)
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE" in alter


def test_a_database_with_another_owner_is_not_taken_over():
    cur = _Cursor(role_exists=True, database_owner="postgres")
    with pytest.raises(DatabaseOwnerError, match="owned by 'postgres'"):
        ensure_role(cur, RoleSpec("ducklake", "ducklake", "pw"))
    assert not any("GRANT ALL" in statement for statement in cur.statements)
