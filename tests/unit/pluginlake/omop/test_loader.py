"""Tests for OMOP data loader."""

from pathlib import Path

import polars as pl
import pytest

from pluginlake.omop.loader import load_omop_table


def test_load_omop_table_file_not_found():
    """Test error handling when CSV file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        load_omop_table(Path("nonexistent.csv"), "person")


def test_load_omop_table_basic(tmp_path):
    """Test basic CSV loading without validation."""
    csv_file = tmp_path / "person.csv"
    csv_file.write_text(
        "person_id,gender_concept_id,year_of_birth,race_concept_id,ethnicity_concept_id\n"
        "1,8507,1980,8527,38003564\n"
        "2,8532,1995,8516,38003564\n"
    )

    df = load_omop_table(csv_file, "person", validate=False)

    expected_rows = 2
    assert len(df) == expected_rows
    assert "person_id" in df.columns
    assert df["person_id"].dtype == pl.Int64
