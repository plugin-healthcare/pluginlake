"""Tests for the Dagster launcher that exports the Postgres password."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from pluginlake.deploy import dagster_env
from pluginlake.deploy.dagster_env import DagsterPostgresSettings
from pluginlake.utils import postgres

FILE_CONTENT = "from-secret"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> DagsterPostgresSettings:
    monkeypatch.setenv("DAGSTER_PG_USER", "dagster")
    monkeypatch.delenv("DAGSTER_PG_PASSWORD", raising=False)
    (tmp_path / "dagster_pg_password").write_text(FILE_CONTENT, encoding="utf-8")
    return DagsterPostgresSettings(_env_file=None, _secrets_dir=tmp_path)  # type: ignore[missing-argument]


def test_module_has_no_toplevel_pluginlake_imports():
    """The production webserver image runs the launcher without pluginlake installed."""
    tree = ast.parse(Path(dagster_env.__file__).read_text(encoding="utf-8"))
    modules = [alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names]
    modules += [node.module or "" for node in tree.body if isinstance(node, ast.ImportFrom)]
    assert not [m for m in modules if m.split(".")[0] == "pluginlake"]


def test_settings_error_lists_missing_fields(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DAGSTER_PG_USER", raising=False)
    monkeypatch.delenv("DAGSTER_PG_PASSWORD", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        DagsterPostgresSettings(_env_file=None)  # type: ignore[missing-argument]
    assert {e["loc"][0] for e in exc_info.value.errors()} == {"user", "password"}


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DAGSTER_PG_USER", "dagster")
    monkeypatch.setenv("DAGSTER_PG_PASSWORD", "from-env")
    s = DagsterPostgresSettings(_env_file=None)  # type: ignore[missing-argument]
    assert s.user == "dagster"
    assert s.password.get_secret_value() == "from-env"


def test_settings_password_from_secret_file(settings: DagsterPostgresSettings):
    assert settings.password.get_secret_value() == FILE_CONTENT


def test_dagster_environ_sets_password(settings: DagsterPostgresSettings):
    env = dagster_env.dagster_environ(settings, {"PATH": "/bin"})
    assert env == {"PATH": "/bin", "DAGSTER_PG_PASSWORD": FILE_CONTENT}


def test_main_without_command_fails():
    with pytest.raises(SystemExit):
        dagster_env.main([])


def test_main_with_incomplete_settings_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DAGSTER_PG_USER", raising=False)
    monkeypatch.delenv("DAGSTER_PG_PASSWORD", raising=False)
    monkeypatch.chdir(Path(__file__).parent)
    assert dagster_env.main(["true"]) == 1


def test_main_execs_command_with_password(monkeypatch: pytest.MonkeyPatch, settings: DagsterPostgresSettings):
    calls: list[tuple] = []
    monkeypatch.setattr(dagster_env, "DagsterPostgresSettings", lambda: settings)
    monkeypatch.setattr(dagster_env.os, "execvpe", lambda *args: calls.append(args))
    dagster_env.main(["dagster-daemon", "run"])
    file, argv, env = calls[0]
    assert (file, argv) == ("dagster-daemon", ["dagster-daemon", "run"])
    assert env["DAGSTER_PG_PASSWORD"] == FILE_CONTENT


def test_main_ensures_database(monkeypatch: pytest.MonkeyPatch, settings: DagsterPostgresSettings):
    created: list[str] = []
    monkeypatch.setattr(dagster_env, "DagsterPostgresSettings", lambda: settings)
    monkeypatch.setattr(postgres, "ensure_database", lambda **kw: created.append(kw["dbname"]))
    monkeypatch.setattr(dagster_env.os, "execvpe", lambda *_args: None)
    dagster_env.main(["--ensure-db", "true"])
    assert created == ["dagster"]
