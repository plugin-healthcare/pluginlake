"""Tests for the CLI entry point."""

from pluginlake.cli.main import main


def test_main_project_new_scaffolds_package(tmp_path):
    assert main(["project", "new", "my-demo", "--dest", str(tmp_path)]) == 0
    assert (tmp_path / "my-demo" / "pyproject.toml").is_file()


def test_main_returns_exit_code_of_command(tmp_path):
    assert main(["project", "new", "Bad_Name", "--dest", str(tmp_path)]) == 1


def test_main_old_init_command_is_gone(tmp_path):
    assert main(["init", "my-demo"]) != 0
