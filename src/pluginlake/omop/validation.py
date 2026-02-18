"""OMOP data validation functions."""

from datetime import date, datetime

import polars as pl

from pluginlake.omop.schemas import get_omop_schema
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def _get_expected_polars_type(annotation: type) -> type[pl.DataType] | None:
    """Map Python type annotation to Polars data type.

    Args:
        annotation: Python type annotation from Pydantic field.

    Returns:
        Polars data type or None if no mapping exists.
    """
    if annotation is int:
        return pl.Int64
    if annotation is str:
        return pl.Utf8
    if annotation is datetime:
        return pl.Datetime
    if annotation is date:
        return pl.Date
    return None


class ValidationError:
    """Represents a validation error."""

    def __init__(self, column: str, message: str, row_index: int | None = None) -> None:
        """Initialize validation error.

        Args:
            column: Column name where error occurred.
            message: Error description.
            row_index: Optional row index where error occurred.
        """
        self.column = column
        self.message = message
        self.row_index = row_index

    def __repr__(self) -> str:
        """String representation of validation error."""
        if self.row_index is not None:
            return f"ValidationError(row={self.row_index}, column={self.column}, message={self.message})"
        return f"ValidationError(column={self.column}, message={self.message})"


def validate_omop_table_schema(
    df: pl.DataFrame,
    table_name: str,
) -> list[ValidationError]:
    """Check DataFrame matches OMOP CDM schema.

    Args:
        df: DataFrame to validate.
        table_name: OMOP table name.

    Returns:
        List of validation errors (empty if valid).
    """
    schema = get_omop_schema(table_name)
    if not schema:
        logger.warning("No schema definition for table: %s", table_name)
        return []

    errors = []
    schema_fields = schema.model_fields
    df_columns = set(df.columns)
    expected_columns = set(schema_fields.keys())

    missing = expected_columns - df_columns
    for col in missing:
        field = schema_fields[col]
        if field.is_required():
            errors.append(ValidationError(col, "Required column missing"))

    unexpected = df_columns - expected_columns
    errors.extend(ValidationError(col, "Unexpected column not in schema") for col in unexpected)

    for col in df_columns & expected_columns:
        field = schema_fields[col]
        df_type = df[col].dtype

        expected_type = _get_expected_polars_type(field.annotation)

        if expected_type and df_type != expected_type:
            errors.append(
                ValidationError(
                    col,
                    f"Type mismatch: expected {expected_type}, got {df_type}",
                )
            )

    return errors
