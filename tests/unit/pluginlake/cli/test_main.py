"""Tests for the CLI entry point."""

from pluginlake.cli.main import main


def test_main_project_new_scaffolds_package(tmp_path):
    assert main(["project", "new", "--name", "my-demo", "--dest", str(tmp_path)]) == 0
    assert (tmp_path / "my-demo" / "pyproject.toml").is_file()


def test_main_returns_exit_code_of_command(tmp_path):
    assert main(["project", "new", "--name", "Bad_Name", "--dest", str(tmp_path)]) == 1


def test_main_old_init_command_is_gone(tmp_path):
    assert main(["init", "my-demo"]) != 0


def test_main_project_new_prompts_without_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    answers = iter(["my-demo", ".", "my_catalog"])
    monkeypatch.setattr("pluginlake.cli.app.typer.prompt", lambda *_a, **_k: next(answers))
    assert main(["project", "new"]) == 0
    manifest = (tmp_path / "my-demo" / "src" / "my_demo" / "manifest.py").read_text()
    assert 'catalog="my_catalog"' in manifest
