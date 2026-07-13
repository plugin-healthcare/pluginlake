"""Tests for ``pluginlake init`` scaffolding."""

import tomllib

from pluginlake.cli.init import run_init


def test_init_scaffolds_expected_tree(tmp_path):
    rc = run_init(name="my-demo", dest=tmp_path)
    assert rc == 0

    project = tmp_path / "my-demo"
    expected = [
        "pyproject.toml",
        "README.md",
        ".gitignore",
        "src/my_demo/__init__.py",
        "src/my_demo/manifest.py",
        "src/my_demo/config.py",
        "src/my_demo/connectors.py",
        "src/my_demo/definitions/__init__.py",
        "src/my_demo/api/routers/example.py",
        "tests/test_conformance.py",
    ]
    for rel in expected:
        assert (project / rel).is_file(), f"missing {rel}"


def test_init_renders_substitutions(tmp_path):
    run_init(name="my-demo", dest=tmp_path)
    project = tmp_path / "my-demo"

    manifest_src = (project / "src/my_demo/manifest.py").read_text()
    assert 'id="my-demo"' in manifest_src
    assert 'catalog="my_demo"' in manifest_src
    assert 'config_prefix="MY_DEMO_"' in manifest_src

    pyproject = tomllib.loads((project / "pyproject.toml").read_text())
    assert pyproject["project"]["name"] == "my-demo"
    assert "my-demo" in pyproject["project"]["entry-points"]["pluginlake.projects"]


def test_init_leaves_no_unrendered_placeholders(tmp_path):
    run_init(name="my-demo", dest=tmp_path)
    for path in (tmp_path / "my-demo").rglob("*"):
        if path.is_file():
            assert "$package_name" not in path.read_text()
            assert "$project_id" not in path.read_text()


def test_init_rejects_invalid_name(tmp_path):
    assert run_init(name="My_Demo", dest=tmp_path) == 1
    assert not (tmp_path / "My_Demo").exists()


def test_init_refuses_existing_target_without_force(tmp_path):
    (tmp_path / "my-demo").mkdir()
    assert run_init(name="my-demo", dest=tmp_path) == 1


def test_init_writes_into_existing_target_with_force(tmp_path):
    (tmp_path / "my-demo").mkdir()
    assert run_init(name="my-demo", dest=tmp_path, force=True) == 0
    assert (tmp_path / "my-demo/pyproject.toml").is_file()
