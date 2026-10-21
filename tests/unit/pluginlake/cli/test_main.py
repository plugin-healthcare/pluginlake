"""Tests for the CLI entry point."""

import builtins

from pluginlake.cli.main import INSTALL_HINT, main


def test_main_shows_install_hint_without_cli_extra(monkeypatch, capsys):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pluginlake.cli.app":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert main(["verify"]) == 1
    assert INSTALL_HINT in capsys.readouterr().err


def test_main_project_new_scaffolds_package(tmp_path):
    assert main(["project", "new", "my-demo", "--dest", str(tmp_path)]) == 0
    assert (tmp_path / "my-demo" / "pyproject.toml").is_file()


def test_main_returns_exit_code_of_command(tmp_path):
    assert main(["project", "new", "Bad_Name", "--dest", str(tmp_path)]) == 1


def test_main_old_init_command_is_gone(tmp_path):
    assert main(["init", "my-demo"]) != 0
