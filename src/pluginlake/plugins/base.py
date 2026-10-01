"""Shared base classes and helpers for project plugins.

Projects depend on ``pluginlake`` and build on these contracts so the platform
can treat every project uniformly (ADR-009):

- :class:`ProjectSettings` — the base for a project's Pydantic Settings.
- :class:`Connector` — the framework-agnostic data-connector contract, a
  generalisation of :class:`pluginlake.core.storage.base.StorageBackend` that
  stays independent of Dagster so both ingestion and the query engine can use it.
- Naming helpers (:func:`asset_urn`, :func:`catalog_table`, :func:`data_path`)
  that encode the catalog-per-project storage layout so projects never hand-roll
  their namespacing.

This module must not import Dagster; it is loaded by the API process too.
"""

from abc import ABC, abstractmethod

import duckdb
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProjectSettings(BaseSettings):
    """Base settings for a project plugin.

    Subclasses set their own environment-variable prefix, matching the
    ``config_prefix`` declared in the project manifest::

        class MyProjectSettings(ProjectSettings):
            model_config = project_settings_config("MYPROJECT_")

            source_url: str = ""

    Using a shared base keeps every project's configuration loading consistent
    (``.env`` support, ``extra="ignore"``) so the conformance suite can load and
    validate it uniformly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def project_settings_config(env_prefix: str) -> SettingsConfigDict:
    """Build a ``SettingsConfigDict`` for a project's settings.

    Args:
        env_prefix: Environment-variable prefix for the project (for example
            ``"EHDS_DEMO_"``). Should match the manifest ``config_prefix``.

    Returns:
        A config dict combining the shared project defaults with ``env_prefix``.
    """
    return SettingsConfigDict(
        env_prefix=env_prefix,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Connector(ABC):
    """Framework-agnostic data-connector contract.

    A connector describes how a project reaches one of its data sources. It is
    deliberately independent of Dagster so the same connector can be used by the
    ingestion path (wrapped in a Dagster resource) and by the DuckDB/DuckLake
    query engine (ADR-009). Connectors loaded into the query-engine process are
    restricted to DuckDB-native capabilities; sources that need arbitrary Python
    are ingest-only.

    Implementations declare a stable ``name`` and configure a DuckDB connection
    so the source is reachable, mirroring
    :class:`pluginlake.core.storage.base.StorageBackend` but for arbitrary
    sources rather than only the DuckLake data path.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return a stable, unique connector name within the project."""

    @abstractmethod
    def configure_duckdb(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Configure a DuckDB connection so this source is reachable.

        Install and load any required extensions, set credentials, and attach
        or register the source as needed.

        Args:
            conn: An open DuckDB connection to configure.
        """


def asset_urn(project: str, layer: str, table: str) -> str:
    """Build the asset URN for a project dataset.

    The URN is the identity used by ODRL permits (ADR-008) and maps one-to-one
    to the project's catalog boundary.

    Args:
        project: Project id (manifest ``id``).
        layer: Medallion layer schema (for example ``"raw"``, ``"processed"``).
        table: Table name within the layer.

    Returns:
        A URN of the form ``urn:pluginlake:{project}:dataset:{layer}:{table}``.
    """
    return f"urn:pluginlake:{project}:dataset:{layer}:{table}"


def catalog_table(catalog: str, layer: str, table: str) -> str:
    """Build a fully-qualified DuckLake table reference.

    Args:
        catalog: The project's DuckLake catalog (manifest ``catalog``).
        layer: Medallion layer schema.
        table: Table name within the layer.

    Returns:
        A reference of the form ``{catalog}.{layer}.{table}``.
    """
    return f"{catalog}.{layer}.{table}"


def data_path(base: str, project: str, layer: str, table: str) -> str:
    """Build the on-storage path for a project table.

    Args:
        base: Root data path (DuckLake ``DATA_PATH``), e.g. ``"s3://bucket"``.
        project: Project id (manifest ``id``).
        layer: Medallion layer schema.
        table: Table name within the layer.

    Returns:
        A POSIX path of the form ``{base}/{project}/{layer}/{table}/``.
    """
    return f"{base.rstrip('/')}/{project}/{layer}/{table}/"
