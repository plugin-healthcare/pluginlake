"""Tests for shared project base classes and naming helpers."""

import duckdb

from pluginlake.plugins.base import (
    Connector,
    ProjectSettings,
    asset_urn,
    catalog_table,
    data_path,
    project_settings_config,
)


def test_asset_urn_format():
    assert asset_urn("ehds-demo", "raw", "patients") == "urn:pluginlake:ehds-demo:dataset:raw:patients"


def test_catalog_table_format():
    assert catalog_table("ducklake", "processed", "omop_person") == "ducklake.processed.omop_person"


def test_data_path_local():
    assert data_path("/srv/data", "ehds-demo", "raw", "patients") == "/srv/data/ehds-demo/raw/patients/"


def test_data_path_preserves_uri_scheme():
    assert data_path("s3://bucket", "proj", "raw", "t") == "s3://bucket/proj/raw/t/"


def test_data_path_strips_trailing_slash_on_base():
    assert data_path("/srv/data/", "proj", "raw", "t") == "/srv/data/proj/raw/t/"


def test_project_settings_config_sets_prefix():
    config = project_settings_config("MYPROJ_")
    assert config["env_prefix"] == "MYPROJ_"
    assert config["extra"] == "ignore"


def test_project_settings_reads_env(monkeypatch):
    class Settings(ProjectSettings):
        model_config = project_settings_config("MYPROJ_")

        source_url: str = ""

    monkeypatch.setenv("MYPROJ_SOURCE_URL", "https://example.test")
    assert Settings().source_url == "https://example.test"


def test_connector_requires_implementation():
    class MyConnector(Connector):
        @property
        def name(self) -> str:
            return "my"

        def configure_duckdb(self, conn: duckdb.DuckDBPyConnection) -> None:
            del conn

    connector = MyConnector()
    assert connector.name == "my"
    assert isinstance(connector, Connector)
