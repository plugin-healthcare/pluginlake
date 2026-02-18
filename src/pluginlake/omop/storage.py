"""OMOP data storage functions.

Handles saving OMOP data to Parquet files and managing DuckDB connections.
"""

import time
from pathlib import Path

import duckdb
import polars as pl

from pluginlake.omop.config import get_omop_settings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def save_omop_table(
    df: pl.DataFrame,
    table_name: str,
    *,
    output_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Save OMOP table as Parquet file.

    Args:
        df: DataFrame to save.
        table_name: OMOP table name (used for filename).
        output_dir: Output directory. Uses config default if None.
        overwrite: Whether to overwrite existing file.

    Returns:
        Path to saved Parquet file.

    Raises:
        FileExistsError: If file exists and overwrite is False.
    """
    settings = get_omop_settings()
    output_dir = output_dir or settings.storage_dir

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{table_name}.parquet"

    if output_path.exists() and not overwrite:
        msg = f"Parquet file already exists: {output_path}"
        logger.error(msg)
        raise FileExistsError(msg)

    start_time = time.time()
    logger.info(
        "Saving OMOP table to Parquet: %s",
        table_name,
        extra={"table_name": table_name, "output_path": str(output_path)},
    )

    df.write_parquet(output_path, compression="zstd")

    duration = time.time() - start_time
    file_size_mb = output_path.stat().st_size / (1024 * 1024)

    logger.info(
        "Saved %s rows to %s (%.1f MB) in %.2fs",
        f"{len(df):,}",
        output_path.name,
        file_size_mb,
        duration,
        extra={
            "table_name": table_name,
            "row_count": len(df),
            "file_size_mb": file_size_mb,
            "duration_seconds": duration,
        },
    )

    return output_path


def get_duckdb_connection(
    db_path: Path | str | None = None,
    *,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Get DuckDB connection.

    Args:
        db_path: Path to DuckDB database file. Uses in-memory if None.
        read_only: Whether to open in read-only mode.

    Returns:
        DuckDB connection.
    """
    if db_path is None:
        logger.debug("Creating in-memory DuckDB connection")
        return duckdb.connect(":memory:")

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug(
        "Opening DuckDB connection: %s (read_only=%s)",
        db_path,
        read_only,
        extra={"db_path": str(db_path), "read_only": read_only},
    )

    return duckdb.connect(str(db_path), read_only=read_only)


def register_omop_tables(
    con: duckdb.DuckDBPyConnection,
    data_dir: Path | None = None,
    *,
    table_names: list[str] | None = None,
) -> list[str]:
    """Register OMOP Parquet files as DuckDB views.

    Args:
        con: DuckDB connection.
        data_dir: Directory containing OMOP Parquet files. Uses config default if None.
        table_names: Specific tables to register. Registers all if None.

    Returns:
        List of registered table names.
    """
    settings = get_omop_settings()
    data_dir = data_dir or settings.storage_dir

    if not data_dir.exists():
        msg = f"OMOP data directory not found: {data_dir}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    parquet_files = list(data_dir.glob("*.parquet"))
    if not parquet_files:
        logger.warning("No Parquet files found in %s", data_dir)
        return []

    registered = []
    for parquet_file in parquet_files:
        table_name = parquet_file.stem

        if table_names and table_name not in table_names:
            continue

        # S608: table_name and parquet_file are controlled by us (from filesystem)
        view_sql = f"""
            CREATE OR REPLACE VIEW {table_name} AS
            SELECT * FROM read_parquet('{parquet_file}')
        """  # noqa: S608

        try:
            con.execute(view_sql)
            registered.append(table_name)
            logger.debug(
                "Registered OMOP table: %s",
                table_name,
                extra={"table_name": table_name, "file_path": str(parquet_file)},
            )
        except Exception:
            logger.exception(
                "Failed to register table: %s",
                table_name,
                extra={"table_name": table_name},
            )

    logger.info(
        "Registered %d OMOP tables",
        len(registered),
        extra={"registered_tables": registered},
    )

    return registered


def load_parquet_as_polars(
    table_name: str,
    data_dir: Path | None = None,
) -> pl.DataFrame:
    """Load OMOP Parquet file as Polars DataFrame.

    Args:
        table_name: OMOP table name.
        data_dir: Directory containing OMOP Parquet files. Uses config default if None.

    Returns:
        Polars DataFrame.

    Raises:
        FileNotFoundError: If Parquet file doesn't exist.
    """
    settings = get_omop_settings()
    data_dir = data_dir or settings.storage_dir

    parquet_path = data_dir / f"{table_name}.parquet"

    if not parquet_path.exists():
        msg = f"OMOP Parquet file not found: {parquet_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    logger.debug("Loading Parquet: %s", table_name, extra={"table_name": table_name})

    return pl.read_parquet(parquet_path)


def query_duckdb(
    con: duckdb.DuckDBPyConnection,
    query: str,
    parameters: list | dict | None = None,
) -> pl.DataFrame:
    """Execute SQL query and return Polars DataFrame.

    Args:
        con: DuckDB connection.
        query: SQL query string with ? placeholders or $name parameters.
        parameters: Query parameters as list (for ?) or dict (for $name).

    Returns:
        Query results as Polars DataFrame.
    """
    logger.debug("Executing DuckDB query", extra={"query": query[:200]})

    if parameters:
        result = con.execute(query, parameters)
    else:
        result = con.execute(query)
    columns = [desc[0] for desc in result.description]
    data = result.fetchall()

    return pl.DataFrame(data, schema=columns, orient="row")
