"""OMOP vocabulary table schemas.

Pydantic models for OMOP vocabulary tables.
Used for validation and type checking.
"""

from pydantic import BaseModel


def get_vocabulary_schema(_table_name: str) -> type[BaseModel] | None:
    """Get Pydantic schema for OMOP vocabulary table.

    Args:
        _table_name: Vocabulary table name (lowercase with underscores).

    Returns:
        Pydantic model class or None if not found.
    """
    return None
