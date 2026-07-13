"""Tests for project plugin discovery."""

import pytest
from fastapi import APIRouter

from pluginlake.plugins.discovery import discover_manifests, load_router
from pluginlake.plugins.manifest import RouterSpec


def test_discovers_in_tree_ehds_demo_project():
    manifests = discover_manifests()
    by_id = {m.id: m for m in manifests}
    assert "ehds-demo" in by_id

    ehds = by_id["ehds-demo"]
    assert ehds.catalog == "ducklake"
    code_modules = {c.module for c in ehds.code_locations}
    assert code_modules == {
        "pluginlake.definitions.omop",
        "pluginlake.definitions.fhir",
    }
    router_modules = {r.module for r in ehds.routers}
    assert "pluginlake.api.routers.omop" in router_modules
    assert "pluginlake.api.routers.fhir" in router_modules


def test_discover_manifests_sorted_by_id():
    ids = [m.id for m in discover_manifests()]
    assert ids == sorted(ids)


def test_load_router_returns_apirouter():
    router = load_router(RouterSpec(module="pluginlake.api.routers.omop"))
    assert isinstance(router, APIRouter)


def test_load_router_rejects_non_router():
    with pytest.raises(TypeError):
        load_router(RouterSpec(module="pluginlake.plugins.manifest", attribute="ProjectManifest"))
