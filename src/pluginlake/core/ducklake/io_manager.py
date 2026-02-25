"""DuckLake IO manager for Dagster assets."""

from typing import TYPE_CHECKING

import polars as pl
from dagster import IOManager, io_manager

from pluginlake.core.ducklake.setup import setup_ducklake
from pluginlake.utils.logger import get_logger

if TYPE_CHECKING:
    import duckdb
    from dagster import InitResourceContext, InputContext, OutputContext

logger = get_logger(__name__)

DEFAULT_SCHEMA = "main"
CATALOG = "ducklake"


class DuckLakeIOManager(IOManager):
    """Dagster IO manager that persists asset outputs to DuckLake.

    Resolves each asset key to a ``catalog.schema.table`` path using
    the full key and an optional schema mapping.

    Default resolution:
        - ``["condition_era"]`` → ``ducklake.main.condition_era``
        - ``["omop", "condition_era"]`` → ``ducklake.omop.condition_era``
        - ``["raw", "omop", "condition_era"]`` → ``ducklake.raw.omop_condition_era``

    With ``schema_mapping={"raw": "bronze"}``:
        - ``["raw", "omop", "condition_era"]`` → ``ducklake.bronze.omop_condition_era``

    Args:
        conn: A DuckDB connection with the ``ducklake`` catalog already attached.
        schema_mapping: Optional mapping from asset key prefix to DuckLake
            schema name. Unmapped prefixes use the prefix itself.
    """

    def __init__(
        self,
        conn: "duckdb.DuckDBPyConnection",
        schema_mapping: dict[str, str] | None = None,
    ) -> None:
        """Initialize with an open DuckDB connection.

        Args:
            conn: A DuckDB connection with the ``ducklake`` catalog attached.
            schema_mapping: Optional mapping from key prefix to schema name.
        """
        self._conn = conn
        self._schema_mapping = schema_mapping or {}

    def resolve_schema(self, prefix: str) -> str:
        """Map an asset key prefix to a DuckLake schema name.

        Args:
            prefix: The first segment of the asset key path.

        Returns:
            The DuckLake schema name (mapped or pass-through).
        """
        return self._schema_mapping.get(prefix, prefix)

    def table_ref(self, asset_key_path: list[str]) -> str:
        """Derive a fully qualified DuckLake table reference from an asset key.

        Uses the full path: first segment becomes the schema (via mapping),
        remaining segments are joined with ``_`` to form the table name.
        Single-segment keys use the default schema.

        Args:
            asset_key_path: The asset key path segments,
                e.g. ``["condition_era"]`` or ``["omop", "condition_era"]``.

        Returns:
            Fully qualified reference like ``ducklake.omop.condition_era``.
        """
        if len(asset_key_path) == 1:
            schema = DEFAULT_SCHEMA
            table = asset_key_path[0]
        else:
            schema = self.resolve_schema(asset_key_path[0])
            table = "_".join(asset_key_path[1:])

        return f"{CATALOG}.{schema}.{table}"

    def _ensure_schema(self, schema: str) -> None:
        """Create the DuckLake schema if it does not exist.

        Args:
            schema: The schema name to ensure exists.
        """
        self._conn.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema}")

    def handle_output(self, context: "OutputContext", obj: pl.DataFrame) -> None:
        """Write a Polars DataFrame to a DuckLake table.

        Ensures the target schema exists, registers the DataFrame with
        DuckDB, and creates or replaces the table.

        Args:
            context: Dagster output context containing the asset key.
            obj: The Polars DataFrame to persist.
        """
        path = list(context.asset_key.path)
        ref = self.table_ref(path)
        schema = ref.split(".")[1]

        self._ensure_schema(schema)

        self._conn.register("_data", obj)
        self._conn.execute(
            f"CREATE OR REPLACE TABLE {ref} AS SELECT * FROM _data"  # noqa: S608
        )
        self._conn.unregister("_data")

        logger.info("Wrote %d rows to %s.", len(obj), ref)

    def load_input(self, context: "InputContext") -> pl.LazyFrame:
        """Load a DuckLake table as a Polars LazyFrame.

        Uses DuckDB's ``pl(lazy=True)`` to return a lazy frame with
        projection and filter pushdown support. Polars operations
        chained on the result are pushed down to DuckDB at collect
        time, enabling DuckLake file pruning.

        Args:
            context: Dagster input context containing the upstream asset key.

        Returns:
            A lazy view of the table. Call ``.collect()`` to materialize.
        """
        ref = self.table_ref(list(context.asset_key.path))
        result = self._conn.sql(f"SELECT * FROM {ref}").pl(lazy=True)  # noqa: S608

        logger.info("Loaded lazy frame from %s.", ref)

        return result


@io_manager
def ducklake_io_manager(_init_context: "InitResourceContext") -> DuckLakeIOManager:
    """Dagster IO manager factory that sets up DuckLake and returns an IO manager.

    Calls :func:`setup_ducklake` to ensure the database exists and
    attach the DuckLake catalog, then wraps the connection in a
    :class:`DuckLakeIOManager`.

    Schema mapping can be configured via DuckLake settings in the future.
    """
    conn = setup_ducklake()
    return DuckLakeIOManager(conn)
