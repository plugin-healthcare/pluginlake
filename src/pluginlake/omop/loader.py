"""OMOP data loading functions."""

import time
from pathlib import Path

import polars as pl

from pluginlake.omop.config import get_omop_settings
from pluginlake.omop.validation import validate_omop_table_schema, validate_vocabulary_table_schema
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

CDM_53_RENAMES = {
    "visit_occurrence": {
        "admitting_source_concept_id": "admitted_from_concept_id",
        "admitting_source_value": "admitted_from_source_value",
        "discharge_to_concept_id": "discharged_to_concept_id",
        "discharge_to_source_value": "discharged_to_source_value",
    },
}

VOCABULARY_FILE_MAPPING = {
    "concept": ["CONCEPT.csv", "concept.csv"],
    "concept_cpt4": ["CONCEPT_CPT4.csv", "concept_cpt4.csv"],
    "vocabulary": ["VOCABULARY.csv", "vocabulary.csv"],
    "domain": ["DOMAIN.csv", "domain.csv"],
    "concept_class": ["CONCEPT_CLASS.csv", "concept_class.csv"],
    "concept_relationship": ["CONCEPT_RELATIONSHIP.csv", "concept_relationship.csv"],
    "relationship": ["RELATIONSHIP.csv", "relationship.csv"],
    "concept_synonym": ["CONCEPT_SYNONYM.csv", "concept_synonym.csv"],
    "concept_ancestor": ["CONCEPT_ANCESTOR.csv", "concept_ancestor.csv"],
    "source_to_concept_map": ["SOURCE_TO_CONCEPT_MAP.csv", "source_to_concept_map.csv"],
    "drug_strength": ["DRUG_STRENGTH.csv", "drug_strength.csv"],
}


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


def _detect_separator(file_path: Path, encoding: str) -> str:
    """Detect delimiter for vocabulary file.

    Args:
        file_path: Path to file.
        encoding: Text encoding.

    Returns:
        Detected separator (tab or comma).
    """
    if file_path.suffix.lower() in {".tsv", ".txt"}:
        return "\t"

    if file_path.name.upper().endswith(".CSV"):
        try:
            first_line = file_path.read_text(encoding=encoding).split("\n")[0]
            if "\t" in first_line and "," not in first_line:
                return "\t"
        except (OSError, UnicodeDecodeError):
            pass

    return ","


def _find_vocabulary_file(
    data_dir: Path,
    table_name: str,
    file_variants: list[str],
) -> Path | None:
    """Find vocabulary file from list of variants.

    Args:
        data_dir: Directory to search in.
        table_name: Table name for logging.
        file_variants: List of filename variants to try.

    Returns:
        Path to found file or None.
    """
    for file_name in file_variants:
        candidate_path = data_dir / file_name
        if candidate_path.exists():
            return candidate_path

    logger.warning(
        "Vocabulary file not found: %s",
        table_name,
        extra={"table_name": table_name, "searched_files": file_variants},
    )
    return None


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
            infer_schema_length=settings.infer_schema_length,
        )

        if table_name in CDM_53_RENAMES:
            renames = {k: v for k, v in CDM_53_RENAMES[table_name].items() if k in df.columns}
            if renames:
                df = df.rename(renames)

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
    *,
    validate: bool = True,
) -> dict[str, pl.DataFrame]:
    """Load multiple OMOP tables from directory.

    Args:
        data_dir: Directory containing OMOP CSV files. Uses config default if None.
        table_names: List of table names to load. Loads all CSV files if None.
        validate: Whether to validate schemas during loading.

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
            tables[table_name] = load_omop_table(csv_file, table_name, validate=validate)
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


def load_vocabulary_table(
    file_path: Path,
    table_name: str,
    *,
    validate: bool | None = None,
    encoding: str | None = None,
) -> pl.DataFrame:
    """Load OMOP vocabulary file into validated Polars DataFrame.

    Args:
        file_path: Path to vocabulary file (CSV or TSV).
        table_name: Vocabulary table name (e.g., 'concept', 'vocabulary').
        validate: Run schema validation. Uses config default if None.
        encoding: File encoding. Uses config default if None.

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
        msg = f"Vocabulary file not found: {file_path}"
        logger.error(msg, extra={"file_path": str(file_path), "table_name": table_name})
        raise FileNotFoundError(msg)

    start_time = time.time()
    logger.info(
        "Loading vocabulary table: %s",
        table_name,
        extra={"file_path": str(file_path), "table_name": table_name},
    )

    try:
        separator = _detect_separator(file_path, encoding)
        df = pl.read_csv(
            file_path,
            encoding=encoding,
            separator=separator,
            quote_char=None,
            null_values=["", "NULL"],
            try_parse_dates=True,
            infer_schema_length=settings.infer_schema_length,
        )

        duration = time.time() - start_time
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        logger.info(
            "Loaded %s rows (%.2f MB) in %.2fs",
            f"{len(df):,}",
            file_size_mb,
            duration,
            extra={
                "table_name": table_name,
                "row_count": len(df),
                "file_size_mb": file_size_mb,
                "duration_seconds": duration,
            },
        )

        if validate:
            errors = validate_vocabulary_table_schema(df, table_name)
            if errors:
                error_summary = errors[:5]
                logger.warning(
                    "Validation found %d issues in vocabulary %s",
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

        return df  # noqa: TRY300

    except Exception:
        logger.exception(
            "Failed to load vocabulary table: %s",
            table_name,
            extra={"table_name": table_name, "file_path": str(file_path)},
        )
        raise


def load_vocabulary_dataset(
    data_dir: Path | None = None,
    table_names: list[str] | None = None,
    *,
    validate: bool = True,
) -> dict[str, pl.DataFrame]:
    """Load OMOP vocabulary tables from directory.

    Args:
        data_dir: Directory containing vocabulary files. Uses config default if None.
        table_names: List of vocabulary table names to load. Loads all if None.
        validate: Whether to validate schemas during loading.

    Returns:
        Dictionary mapping table names to DataFrames.
    """
    settings = get_omop_settings()
    data_dir = data_dir or settings.vocabulary_dir

    if not data_dir.exists():
        msg = f"Vocabulary directory not found: {data_dir}"
        logger.warning(msg, extra={"data_dir": str(data_dir)})
        return {}

    vocabulary_files = VOCABULARY_FILE_MAPPING
    if table_names:
        include = set(table_names)
        if "concept" in include:
            include.add("concept_cpt4")
        vocabulary_files = {k: v for k, v in vocabulary_files.items() if k in include}

    logger.info(
        "Loading OMOP vocabularies from %s",
        data_dir,
        extra={"data_dir": str(data_dir), "table_count": len(vocabulary_files)},
    )

    tables = {}
    for table_name, file_variants in vocabulary_files.items():
        file_path = _find_vocabulary_file(data_dir, table_name, file_variants)
        if not file_path:
            continue

        try:
            tables[table_name] = load_vocabulary_table(file_path, table_name, validate=validate)
        except (FileNotFoundError, ValueError, OSError):
            logger.exception(
                "Skipping vocabulary table %s due to error",
                table_name,
                extra={"table_name": table_name},
            )

    if "concept_cpt4" in tables:
        if "concept" in tables:
            tables["concept"] = pl.concat([tables["concept"], tables.pop("concept_cpt4")])
            logger.info("Merged concept_cpt4 into concept.")
        else:
            tables.pop("concept_cpt4")

    logger.info(
        "Loaded %d vocabulary tables",
        len(tables),
        extra={"loaded_tables": list(tables.keys())},
    )

    return tables
