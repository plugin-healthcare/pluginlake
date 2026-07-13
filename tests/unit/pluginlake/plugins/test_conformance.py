"""Tests for the project conformance suite."""

import sys
import types

import duckdb
import pytest
from dagster import Definitions
from fastapi import APIRouter

from pluginlake.plugins.base import Connector, ProjectSettings, project_settings_config
from pluginlake.plugins.conformance import ConformanceError, verify_all, verify_manifest
from pluginlake.plugins.manifest import (
    CodeLocationSpec,
    ConnectorSpec,
    ProjectManifest,
    RouterSpec,
    SettingsSpec,
)

STUB_MODULE = "pluginlake_test_stub_project"


@pytest.fixture
def stub_module():
    """Register an importable module exposing conformant project contributions."""
    mod = types.ModuleType(STUB_MODULE)

    class StubConnector(Connector):
        @property
        def name(self) -> str:
            return "stub"

        def configure_duckdb(self, conn: duckdb.DuckDBPyConnection) -> None:
            del conn

    class StubSettings(ProjectSettings):
        model_config = project_settings_config("STUB_")

        value: str = "default"

    for attr, value in {
        "router": APIRouter(),
        "defs": Definitions(),
        "StubConnector": StubConnector,
        "Settings": StubSettings,
    }.items():
        setattr(mod, attr, value)
    sys.modules[STUB_MODULE] = mod
    yield mod
    del sys.modules[STUB_MODULE]


def _conformant_manifest() -> ProjectManifest:
    return ProjectManifest(
        id="stub",
        catalog="stub",
        namespace="stub",
        config_prefix="STUB_",
        requires_core=">=0.1.0,<0.2.0",
        code_locations=[CodeLocationSpec(module=STUB_MODULE)],
        routers=[RouterSpec(module=STUB_MODULE)],
        connectors=[ConnectorSpec(module=STUB_MODULE, attribute="StubConnector")],
        settings=SettingsSpec(module=STUB_MODULE),
    )


def test_conformant_manifest_has_no_issues(stub_module):
    assert verify_manifest(_conformant_manifest(), installed_core="0.1.5") == []


def test_incompatible_core_version_is_flagged(stub_module):
    manifest = _conformant_manifest()
    issues = verify_manifest(manifest, installed_core="0.5.0")
    assert any("requires core" in i.message for i in issues)


def test_invalid_core_specifier_is_flagged():
    manifest = ProjectManifest(id="p", catalog="p", namespace="p", config_prefix="P_", requires_core="not-a-spec")
    issues = verify_manifest(manifest, installed_core="0.1.0")
    assert any("PEP 440" in i.message for i in issues)


def test_missing_module_is_flagged():
    manifest = ProjectManifest(
        id="p",
        catalog="p",
        namespace="p",
        config_prefix="P_",
        routers=[RouterSpec(module="does.not.exist")],
    )
    issues = verify_manifest(manifest, installed_core="0.1.0")
    assert any("failed to load" in i.message for i in issues)


def test_router_of_wrong_type_is_flagged():
    manifest = ProjectManifest(
        id="p",
        catalog="p",
        namespace="p",
        config_prefix="P_",
        routers=[RouterSpec(module="pluginlake.plugins.manifest", attribute="ProjectManifest")],
    )
    issues = verify_manifest(manifest, installed_core="0.1.0")
    assert any("not an APIRouter" in i.message for i in issues)


def test_connector_of_wrong_type_is_flagged():
    manifest = ProjectManifest(
        id="p",
        catalog="p",
        namespace="p",
        config_prefix="P_",
        connectors=[ConnectorSpec(module="pluginlake.plugins.manifest", attribute="ProjectManifest")],
    )
    issues = verify_manifest(manifest, installed_core="0.1.0")
    assert any("Connector subclass" in i.message for i in issues)


def test_settings_of_wrong_type_is_flagged():
    manifest = ProjectManifest(
        id="p",
        catalog="p",
        namespace="p",
        config_prefix="P_",
        settings=SettingsSpec(module="pluginlake.plugins.manifest", attribute="ProjectManifest"),
    )
    issues = verify_manifest(manifest, installed_core="0.1.0")
    assert any("ProjectSettings subclass" in i.message for i in issues)


def test_duplicate_catalog_is_flagged_across_projects():
    a = ProjectManifest(id="a", catalog="shared", namespace="a", config_prefix="A_")
    b = ProjectManifest(id="b", catalog="shared", namespace="b", config_prefix="B_")
    report = verify_all([a, b], installed_core="0.1.0")
    assert not report.ok
    assert any("catalog" in i.message for i in report.issues)


def test_duplicate_namespace_is_flagged_across_projects():
    a = ProjectManifest(id="a", catalog="a", namespace="shared", config_prefix="A_")
    b = ProjectManifest(id="b", catalog="b", namespace="shared", config_prefix="B_")
    report = verify_all([a, b], installed_core="0.1.0")
    assert any("namespace" in i.message for i in report.issues)


def test_verify_all_ok_for_distinct_conformant_projects(stub_module):
    a = _conformant_manifest()
    report = verify_all([a], installed_core="0.1.5")
    assert report.ok
    assert report.format() == "All projects conform."


def test_raise_for_status_raises_on_failure():
    a = ProjectManifest(id="a", catalog="a", namespace="a", config_prefix="A_", requires_core=">=99.0.0")
    report = verify_all([a], installed_core="0.1.0")
    with pytest.raises(ConformanceError):
        report.raise_for_status()
