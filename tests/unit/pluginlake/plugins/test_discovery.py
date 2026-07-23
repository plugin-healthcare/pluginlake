"""Tests for project plugin discovery."""

import pytest
from fastapi import APIRouter

from pluginlake.plugins.discovery import discover_manifests, load_router
from pluginlake.plugins.manifest import ProjectManifest, RouterSpec


def test_discover_manifests_returns_manifests():
    manifests = discover_manifests()
    assert isinstance(manifests, list)
    assert all(isinstance(m, ProjectManifest) for m in manifests)


def test_discover_manifests_sorted_by_id():
    ids = [m.id for m in discover_manifests()]
    assert ids == sorted(ids)


def test_load_router_returns_apirouter():
    router = load_router(RouterSpec(module="pluginlake.api.routers.health"))
    assert isinstance(router, APIRouter)


def test_load_router_rejects_non_router():
    with pytest.raises(TypeError):
        load_router(RouterSpec(module="pluginlake.plugins.manifest", attribute="ProjectManifest"))
