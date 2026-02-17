"""OMOP data loading functions."""

import time
from pathlib import Path

import polars as pl

from pluginlake.omop.config import get_omop_settings
from pluginlake.omop.validation import validate_omop_table_schema
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def _raise_validation_error(table_name: str, error_count: int) -> None:
    """Raise validation error with formatted message.

    Args:
        table_name: Name of the OMOP table.
        error_count: Number of validation errors.

    Raises:
        ValueError: Always raised with formatted error message.
    """
    msg = f"Validation failed for {table_name}: {error_count} errors"
    raise ValueError(msg)


def load_omop_table(
    file_path: Path,
    table_name: str,
    *,
    validate: bool | None = None,
    encoding: str | None = None,
) -> pl.DataFrame:
    """Load OMOP CSV into validated Polars DataFrame.

    Args:
        file_path: Path to CSV file.
        table_name: OMOP table name (e.g., 'person', 'condition_occurrence').
        validate: Run schema validation. Uses config default if None.
        encoding: CSV encoding. Uses config default if None.

    Returns:
        Polars DataFrame with validated schema.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If validation fails and skip_invalid_rows is False.
    """
    settings = get_omop_settings()
    validate = validate if validate is not None else settings.validate_on_load
    encoding = encoding or settings.csv_encoding

    if not file_path.exists():
        msg = f"OMOP CSV file not found: {file_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    start_time = time.time()
    logger.info(
        "Loading OMOP table: %s",
        table_name,
        extra={"file_path": str(file_path), "table_name": table_name},
    )

    try:
        df = pl.read_csv(
            file_path,
            encoding=encoding,
            null_values=["", "NULL"],
            try_parse_dates=True,
        )

        duration = time.time() - start_time
        logger.info(
            "Loaded %s rows in %.2fs",
            f"{len(df):,}",
            duration,
            extra={
                "table_name": table_name,
                "row_count": len(df),
                "duration_seconds": duration,
            },
        )

        if validate:
            errors = validate_omop_table_schema(df, table_name)
            if errors:
                error_summary = errors[:5]  # Log first 5 errors
                logger.warning(
                    "Validation found %d issues in %s",
                    len(errors),
                    table_name,
                    extra={
                        "table_name": table_name,
                        "error_count": len(errors),
                        "sample_errors": error_summary,
                    },
                )
                if not settings.skip_invalid_rows:
                    _raise_validation_error(table_name, len(errors))
            # Either no errors or skip_invalid_rows is True - continue to return
        # Return the DataFrame (validated or not)
        return df  # noqa: TRY300

    except Exception:
        logger.exception(
            "Failed to load OMOP table: %s",
            table_name,
            extra={"table_name": table_name, "file_path": str(file_path)},
        )
        raise


def load_omop_dataset(
    data_dir: Path | None = None,
    table_names: list[str] | None = None,
) -> dict[str, pl.DataFrame]:
    """Load multiple OMOP tables from directory.

    Args:
        data_dir: Directory containing OMOP CSV files. Uses config default if None.
        table_names: List of table names to load. Loads all CSV files if None.

    Returns:
        Dictionary mapping table names to DataFrames.
    """
    settings = get_omop_settings()
    data_dir = data_dir or settings.raw_data_dir

    if not data_dir.exists():
        msg = f"OMOP data directory not found: {data_dir}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    csv_files = list(data_dir.glob("*.csv"))
    if not csv_files:
        msg = f"No CSV files found in {data_dir}"
        logger.warning(msg)
        return {}

    logger.info(
        "Loading OMOP dataset from %s",
        data_dir,
        extra={"data_dir": str(data_dir), "csv_count": len(csv_files)},
    )

    tables = {}
    for csv_file in csv_files:
        table_name = csv_file.stem.lower()

        if table_names and table_name not in table_names:
            continue

        try:
            tables[table_name] = load_omop_table(csv_file, table_name)
        except (FileNotFoundError, ValueError, OSError):
            logger.exception(
                "Skipping table %s due to error",
                table_name,
                extra={"table_name": table_name},
            )

    logger.info(
        "Loaded %d OMOP tables",
        len(tables),
        extra={"loaded_tables": list(tables.keys())},
    )

    return tables
