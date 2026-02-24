"""Tests for pluginlake.core.storage.layers."""

from pathlib import Path

import pytest

from pluginlake.config import StorageLayer, StorageSettings
from pluginlake.core.storage.layers import StorageLayerManager
from pluginlake.core.storage.local import LocalStorageBackend


@pytest.fixture
def storage_settings(tmp_path: Path) -> StorageSettings:
    return StorageSettings(base_dir=tmp_path / "lake")


@pytest.fixture
def manager(storage_settings: StorageSettings) -> StorageLayerManager:
    return StorageLayerManager(settings=storage_settings)


def test_initialize_creates_all_layer_dirs(manager: StorageLayerManager):
    manager.initialize()
    assert manager.raw_dir.is_dir()
    assert manager.processed_dir.is_dir()
    assert manager.output_dir.is_dir()


def test_initialize_is_idempotent(manager: StorageLayerManager):
    manager.initialize()
    manager.initialize()  # should not raise
    assert manager.raw_dir.is_dir()


def test_get_path_with_parts(manager: StorageLayerManager):
    path = manager.get_path(StorageLayer.RAW, "patients", "data.parquet")
    assert path == manager.settings.base_dir / "raw" / "patients" / "data.parquet"


def test_get_path_layer_only(manager: StorageLayerManager):
    path = manager.get_path(StorageLayer.OUTPUT)
    assert path == manager.settings.base_dir / "output"


def test_shortcut_properties_match_settings(manager: StorageLayerManager):
    assert manager.raw_dir == manager.settings.raw_dir
    assert manager.processed_dir == manager.settings.processed_dir
    assert manager.output_dir == manager.settings.output_dir


def test_default_backend_is_local(manager: StorageLayerManager):
    assert isinstance(manager.backend, LocalStorageBackend)


def test_custom_backend_override(storage_settings: StorageSettings, tmp_path: Path):
    custom = LocalStorageBackend(tmp_path / "custom")
    mgr = StorageLayerManager(settings=storage_settings, backend=custom)
    assert mgr.backend is custom


def test_unsupported_backend_raises():
    settings = StorageSettings(backend="local")
    # Monkey-patch to simulate an unsupported backend
    object.__setattr__(settings, "backend", "s3")
    with pytest.raises(ValueError, match="Unsupported storage backend"):
        StorageLayerManager(settings=settings)


def test_default_settings_when_none():
    mgr = StorageLayerManager()
    assert mgr.settings.base_dir.is_absolute()
    assert mgr.settings.backend == "local"
