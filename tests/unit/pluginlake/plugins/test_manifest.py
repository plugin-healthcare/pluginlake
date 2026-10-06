"""Tests for the ProjectManifest model."""

import pytest
from pydantic import ValidationError

from pluginlake.plugins.manifest import CodeLocationSpec, ProjectManifest, RouterSpec


def test_manifest_builds_with_declared_contributions():
    manifest = ProjectManifest(
        id="ehds-demo",
        catalog="ducklake",
        namespace="ehds-demo",
        config_prefix="EHDS_DEMO_",
        code_locations=[CodeLocationSpec(module="pkg.defs")],
        routers=[RouterSpec(module="pkg.routers.thing")],
    )
    assert manifest.id == "ehds-demo"
    assert manifest.code_locations[0].attribute == "defs"
    assert manifest.routers[0].attribute == "router"


def test_manifest_defaults_are_empty():
    manifest = ProjectManifest(id="p", catalog="p", namespace="p", config_prefix="P_")
    assert manifest.code_locations == []
    assert manifest.routers == []
    assert manifest.requires_core == ""


@pytest.mark.parametrize("bad_id", ["EHDS", "1demo", "ehds_demo", "ehds demo"])
def test_manifest_rejects_invalid_id(bad_id):
    with pytest.raises(ValidationError):
        ProjectManifest(id=bad_id, catalog="c", namespace="n", config_prefix="P_")


@pytest.mark.parametrize("bad_catalog", ["Ducklake", "1cat", "cat-alog"])
def test_manifest_rejects_invalid_catalog(bad_catalog):
    with pytest.raises(ValidationError):
        ProjectManifest(id="p", catalog=bad_catalog, namespace="n", config_prefix="P_")
