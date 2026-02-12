from pathlib import Path

import dagster as dg
import duckdb
import polars as pl
import yaml

# Define root directory
root = Path(__file__).parent.parent.parent.parent

# Vocabulary data paths - OHDSI vocabulary directories
VOCAB_DATA_DIRS = [
    root / "data" / "vocabularies" / "athena",  # Main OHDSI Athena vocabularies
    root / "data" / "vocabularies" / "custom",  # Custom vocabularies if any
]


@dg.asset
def assets(context: dg.AssetExecutionContext) -> dg.MaterializeResult: ...


def _discover_vocabulary_files() -> list[tuple[str, Path]]:
    """Discover all vocabulary files in the configured directories.

    Returns:
        List of (table_name, file_path) tuples
    """
    vocab_files = []

    for vocab_dir in VOCAB_DATA_DIRS:
        if not vocab_dir.exists():
            continue

        # Scan for CSV files
        for file_path in vocab_dir.rglob("*.csv"):
            table_name = file_path.stem.lower()
            vocab_files.append((table_name, file_path))

        # Scan for TSV/TXT files (common in OHDSI vocabularies)
        for file_path in vocab_dir.rglob("*.txt"):
            table_name = file_path.stem.lower()
            vocab_files.append((table_name, file_path))

    return vocab_files


def build_vocabulary_asset(table_name: str, file_path: Path) -> dg.AssetsDefinition:
    """Build a Dagster asset for a single vocabulary table.

    Args:
        table_name: Name of the vocabulary table
        file_path: Path to the source CSV/TSV file

    Returns:
        Dagster asset definition
    """
    asset_key = f"vocab_{table_name}"

    @dg.asset(
        name=asset_key,
        io_manager_key="vocab_polars_parquet_io_manager",
        description=f"OHDSI vocabulary table: {table_name}",
        group_name="OMOP",
        kinds={"polars", "parquet"},
        metadata={
            "source_file": str(file_path),
            "table_name": table_name,
        },
    )
    def vocabulary_asset(context: dg.AssetExecutionContext) -> pl.DataFrame:
        """Load vocabulary table from source file."""
        context.log.info(f"📚 Loading {table_name} from {file_path.name}")

        try:
            # Determine separator based on file extension
            separator = "\t"

            # Load with Polars - handle ragged lines and encoding issues
            df = pl.read_csv(
                file_path,
                separator=separator,
                try_parse_dates=True,
                truncate_ragged_lines=True,  # Handle rows with extra columns
                ignore_errors=True,  # Skip rows that can't be parsed
                encoding="utf8-lossy",  # Handle encoding issues gracefully
                quote_char=None,  # CSVs contain quotes!
            )

            context.log.info(f"✅ Loaded {table_name}: {len(df):,} rows, {len(df.columns)} columns")

            return df

        except Exception as e:
            context.log.error(f"❌ Failed to load {table_name} from {file_path}: {e}")
            raise

    return vocabulary_asset


def build_cbs_job(table_id: str) -> dg.Definitions:
    asset_key = f"cbs-{table_id}"

    @dg.asset(
        name=asset_key,
        io_manager_key="cbs_polars_parquet_io_manager",
        group_name="CBS",
        kinds={"polars", "parquet"},
    )
    def build_cbs_asset(context, cbs: dg.ConfigurableResource) -> pl.DataFrame:
        return pl.DataFrame(cbs.get_data(table_id))

    return dg.Definitions(
        assets=[build_cbs_asset],
    )


def load_cbs_job_from_yaml(yaml_path: str) -> dg.Definitions:
    config = yaml.safe_load(open(yaml_path))
    defs = []
    for table in config["tables"]:
        defs.append(build_cbs_job(table))
    return dg.Definitions.merge(*defs)


def build_omop_duckdb_asset(vocab_files: list[tuple[str, Path]]) -> dg.AssetsDefinition:
    """Build a DuckDB asset that combines all OMOP vocabulary tables.

    Args:
        vocab_files: List of (table_name, file_path) tuples

    Returns:
        Dagster asset definition for the combined DuckDB database
    """
    # Create list of upstream asset keys
    upstream_assets = [dg.AssetKey(f"vocab_{table_name}") for table_name, _ in vocab_files]

    @dg.asset(
        name="omop_vocabularies_duckdb",
        deps=upstream_assets,
        description="Combined OMOP vocabulary tables in DuckDB format",
        group_name="OMOP",
        kinds={"duckdb"},
        metadata={
            "num_tables": len(vocab_files),
            "table_names": [table_name for table_name, _ in vocab_files],
        },
    )
    def omop_vocabularies_duckdb(context: dg.AssetExecutionContext) -> None:
        """Combine all vocabulary parquet files into a single DuckDB database."""
        db_path = root / "datalake" / "vocabularies" / "omop-vocabularies.duckdb"

        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing database if present
        if db_path.exists():
            db_path.unlink()

        context.log.info(f"🦆 Creating DuckDB database at {db_path}")

        # Connect to DuckDB
        con = duckdb.connect(str(db_path))

        try:
            # Get the base directory for parquet files
            parquet_base_dir = root / "datalake" / "vocabularies"

            # Import each vocabulary table
            for table_name, _ in vocab_files:
                parquet_path = parquet_base_dir / f"vocab_{table_name}.parquet"

                if parquet_path.exists():
                    context.log.info(f"📥 Loading {table_name} into DuckDB")

                    # Read parquet and create table in DuckDB
                    con.execute(f"""
                        CREATE TABLE {table_name} AS
                        SELECT * FROM read_parquet('{parquet_path}')
                    """)

                    # Get row count for logging
                    row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                    context.log.info(f"✅ Loaded {table_name}: {row_count:,} rows")
                else:
                    context.log.warning(f"⚠️  Parquet file not found for {table_name}")

            # Get database stats
            tables = con.execute("SHOW TABLES").fetchall()
            total_size = db_path.stat().st_size / (1024 * 1024)  # MB

            context.log.info(f"🎉 Created DuckDB with {len(tables)} tables, size: {total_size:.2f} MB")

        finally:
            con.close()

    return omop_vocabularies_duckdb


@dg.definitions
def vocab_defs():
    """Vocabulary asset definitions - dynamically created from source files"""
    vocab_files = _discover_vocabulary_files()

    if not vocab_files:
        # Return empty definitions if no vocab files found
        return dg.Definitions(assets=[])

    # Build an asset for each vocabulary file
    vocab_assets = [build_vocabulary_asset(table_name, file_path) for table_name, file_path in vocab_files]

    # Add the combined DuckDB asset
    vocab_assets.append(build_omop_duckdb_asset(vocab_files))

    return dg.Definitions(assets=vocab_assets)


@dg.definitions
def cbs_defs():
    """CBS asset definitions from YAML configuration"""
    return load_cbs_job_from_yaml("cbs_load_job.yaml")
