"""Storage layer manager for the medallion architecture.

Provides a high-level interface for working with the raw / processed / output
storage layers on top of a :class:`~pluginlake.core.storage.base.StorageBackend`.
"""

from pathlib import Path

from pluginlake.config import StorageLayer, StorageSettings
from pluginlake.core.storage.base import StorageBackend
from pluginlake.core.storage.local import LocalStorageBackend
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


class StorageLayerManager:
    """Manages the medallion-architecture directory structure.

    Wraps a :class:`StorageBackend` and the corresponding
    :class:`StorageSettings` to provide layer-aware path resolution
    and directory initialisation.

    Args:
        settings: Storage configuration with layer paths.
        backend: Optional storage backend override.  When *None*, the
            backend is resolved from ``settings.backend``.

    Raises:
        ValueError: If the configured storage backend is not supported.
    """

    def __init__(
        self,
        settings: StorageSettings | None = None,
        backend: StorageBackend | None = None,
    ) -> None:
        """Initialise with storage settings and an optional backend override."""
        self._settings = settings or StorageSettings()
        self._backend = backend or self._resolve_backend()

    # -- Public API ----------------------------------------------------------

    def initialize(self) -> None:
        """Create **all** storage layer directories.

        Idempotent — safe to call multiple times.
        """
        self._settings.ensure_directories()
        logger.info(
            "Storage layers initialised under %s: %s",
            self._settings.base_dir,
            [layer.value for layer in StorageLayer],
        )

    def get_path(self, layer: StorageLayer, *parts: str) -> Path:
        """Return a path within a specific storage layer.

        Args:
            layer: Target storage layer.
            *parts: Additional path segments appended after the layer dir.

        Returns:
            Absolute path for the requested resource.
        """
        return self._settings.get_layer_path(layer, *parts)

    @property
    def raw_dir(self) -> Path:
        """Shortcut to the raw (bronze) layer directory."""
        return self._settings.raw_dir

    @property
    def processed_dir(self) -> Path:
        """Shortcut to the processed (silver) layer directory."""
        return self._settings.processed_dir

    @property
    def output_dir(self) -> Path:
        """Shortcut to the output (gold) layer directory."""
        return self._settings.output_dir

    @property
    def backend(self) -> StorageBackend:
        """The underlying storage backend."""
        return self._backend

    @property
    def settings(self) -> StorageSettings:
        """The active storage settings."""
        return self._settings

    # -- Internal ------------------------------------------------------------

    def _resolve_backend(self) -> StorageBackend:
        """Instantiate the storage backend from settings."""
        kind = self._settings.backend.lower()
        if kind == "local":
            return LocalStorageBackend(self._settings.base_dir)
        msg = f"Unsupported storage backend: {kind!r}. Supported: 'local'."
        raise ValueError(msg)
