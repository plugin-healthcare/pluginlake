"""FHIR NDJSON loading functions."""

from pathlib import Path

import orjson
import polars as pl

from pluginlake.fhir.config import get_fhir_settings
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def load_fhir_ndjson(file_path: Path) -> pl.DataFrame:
    """Load a FHIR NDJSON file into a single-column DataFrame.

    Each line is stored as a JSON string in the ``json_data`` column.
    Empty lines and lines that fail to parse are skipped.

    Args:
        file_path: Path to the NDJSON file.

    Returns:
        Polars DataFrame with a single ``json_data`` (Utf8) column.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not file_path.exists():
        msg = f"FHIR NDJSON file not found: {file_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    logger.info("Loading FHIR NDJSON: %s", file_path)

    rows: list[str] = []
    with file_path.open("rb") as f:
        for lineno, raw_line in enumerate(f, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                orjson.loads(stripped)
            except orjson.JSONDecodeError:
                logger.warning("Skipping invalid JSON at line %d in %s", lineno, file_path)
                continue
            rows.append(stripped.decode("utf-8"))

    logger.info("Loaded %d FHIR resources from %s", len(rows), file_path)
    return pl.DataFrame({"json_data": rows}, schema={"json_data": pl.Utf8})


def load_fhir_dataset(
    data_dir: Path | None = None,
    resource_types: list[str] | None = None,
) -> dict[str, pl.DataFrame]:
    """Load multiple FHIR NDJSON files from a directory.

    Each file is expected to be named ``{resource_type}.ndjson``.

    Args:
        data_dir: Directory containing NDJSON files. Uses config default if None.
        resource_types: List of resource types to load. Loads all NDJSON files if None.

    Returns:
        Dictionary mapping resource type names to DataFrames.
    """
    settings = get_fhir_settings()
    data_dir = data_dir or settings.raw_data_dir

    if not data_dir.exists():
        msg = f"FHIR data directory not found: {data_dir}"
        logger.warning(msg)
        return {}

    ndjson_files = list(data_dir.glob("*.ndjson"))
    if not ndjson_files:
        logger.warning("No NDJSON files found in %s", data_dir)
        return {}

    tables: dict[str, pl.DataFrame] = {}
    for ndjson_file in ndjson_files:
        resource_type = ndjson_file.stem.lower()
        if resource_types and resource_type not in resource_types:
            continue
        try:
            tables[resource_type] = load_fhir_ndjson(ndjson_file)
        except (FileNotFoundError, OSError):
            logger.exception("Skipping %s due to error", resource_type)

    logger.info("Loaded %d FHIR resource files", len(tables))
    return tables
