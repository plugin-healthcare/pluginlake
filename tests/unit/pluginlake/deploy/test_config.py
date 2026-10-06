"""Tests for the station deployment config (``pluginlake.toml``)."""

from pathlib import Path

import pytest

from pluginlake.deploy.config import ProjectSpec, StationConfig, load_station_config


def test_local_project_install_spec():
    project = ProjectSpec(name="ehds-demo", path=Path("../pluginlake-ehds-demo"))
    assert project.is_local
    assert project.install_spec() == "-e /opt/projects/pluginlake-ehds-demo"


def test_source_project_install_spec():
    project = ProjectSpec(name="x", source="x @ git+https://example.com/x@v1")
    assert not project.is_local
    assert project.install_spec() == "x @ git+https://example.com/x@v1"


def test_requires_exactly_one_origin():
    with pytest.raises(ValueError, match="exactly one"):
        ProjectSpec(name="x")
    with pytest.raises(ValueError, match="exactly one"):
        ProjectSpec(name="x", path=Path("a"), source="b==1.0")


def test_projects_env_joins_specs():
    config = StationConfig(
        projects=[
            ProjectSpec(name="a", path=Path("../a")),
            ProjectSpec(name="b", source="b==1.0"),
        ]
    )
    assert config.projects_env() == "-e /opt/projects/a b==1.0"
    assert [p.name for p in config.local_projects] == ["a"]


def test_duplicate_names_rejected():
    with pytest.raises(ValueError, match="duplicate project names"):
        StationConfig(
            projects=[
                ProjectSpec(name="a", path=Path("../a")),
                ProjectSpec(name="a", source="a==1.0"),
            ]
        )


def test_load_station_config(tmp_path: Path):
    toml = tmp_path / "pluginlake.toml"
    toml.write_text(
        '[station]\nendpoint_url = "http://x"\n\n[[projects]]\nname = "ehds-demo"\npath = "../pluginlake-ehds-demo"\n',
        encoding="utf-8",
    )
    config = load_station_config(toml)
    assert config.station.endpoint_url == "http://x"
    assert config.station.dashboards is True
    assert config.projects[0].name == "ehds-demo"
    assert config.projects_env() == "-e /opt/projects/pluginlake-ehds-demo"


def test_load_missing_config_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_station_config(tmp_path / "nope.toml")
