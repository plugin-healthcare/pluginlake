"""Tests for vocabulary loader functions."""

from datetime import date

import polars as pl
import pytest

from pluginlake.omop.loader import load_vocabulary_dataset, load_vocabulary_table


def test_load_vocabulary_table_csv(tmp_path, sample_concepts):
    csv_file = tmp_path / "CONCEPT.csv"
    sample_concepts.write_csv(csv_file)

    result = load_vocabulary_table(csv_file, "concept", validate=False)

    assert result.height == sample_concepts.height
    assert set(result.columns) == set(sample_concepts.columns)


def test_load_vocabulary_table_tsv(tmp_path, sample_concepts):
    tsv_file = tmp_path / "CONCEPT.tsv"
    with tsv_file.open("w") as f:
        f.write("\t".join(sample_concepts.columns) + "\n")
        for row in sample_concepts.iter_rows():
            f.write("\t".join(str(v) if v is not None else "" for v in row) + "\n")

    result = load_vocabulary_table(tsv_file, "concept", validate=False)

    assert result.height == sample_concepts.height


def test_load_vocabulary_table_csv_with_tabs(tmp_path, sample_concepts):
    csv_file = tmp_path / "CONCEPT.csv"
    with csv_file.open("w") as f:
        f.write("\t".join(sample_concepts.columns) + "\n")
        for row in sample_concepts.iter_rows():
            f.write("\t".join(str(v) if v is not None else "" for v in row) + "\n")

    result = load_vocabulary_table(csv_file, "concept", validate=False)

    assert result.height == sample_concepts.height


def test_load_vocabulary_table_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="Vocabulary file not found"):
        load_vocabulary_table(tmp_path / "nonexistent.csv", "concept")


def test_load_vocabulary_table_with_validation(tmp_path, sample_concepts):
    csv_file = tmp_path / "CONCEPT.csv"
    sample_concepts.write_csv(csv_file)

    result = load_vocabulary_table(csv_file, "concept", validate=True)

    assert result.height == sample_concepts.height


def test_load_vocabulary_dataset_all_tables(tmp_path, sample_concepts, sample_vocabularies, sample_domains):
    vocab_dir = tmp_path / "vocabularies"
    vocab_dir.mkdir()

    sample_concepts.write_csv(vocab_dir / "CONCEPT.csv")
    sample_vocabularies.write_csv(vocab_dir / "VOCABULARY.csv")
    sample_domains.write_csv(vocab_dir / "DOMAIN.csv")

    result = load_vocabulary_dataset(vocab_dir, validate=False)

    assert "concept" in result
    assert "vocabulary" in result
    assert "domain" in result
    assert result["concept"].height == sample_concepts.height


def test_load_vocabulary_dataset_specific_tables(tmp_path, sample_concepts, sample_vocabularies):
    vocab_dir = tmp_path / "vocabularies"
    vocab_dir.mkdir()

    sample_concepts.write_csv(vocab_dir / "CONCEPT.csv")
    sample_vocabularies.write_csv(vocab_dir / "VOCABULARY.csv")

    result = load_vocabulary_dataset(vocab_dir, table_names=["concept"], validate=False)

    assert "concept" in result
    assert "vocabulary" not in result


def test_load_vocabulary_dataset_lowercase_filenames(tmp_path, sample_concepts):
    vocab_dir = tmp_path / "vocabularies"
    vocab_dir.mkdir()

    sample_concepts.write_csv(vocab_dir / "concept.csv")

    result = load_vocabulary_dataset(vocab_dir, validate=False)

    assert "concept" in result


def test_load_vocabulary_dataset_missing_directory(tmp_path):
    result = load_vocabulary_dataset(tmp_path / "nonexistent", validate=False)

    assert result == {}


def test_load_vocabulary_dataset_empty_directory(tmp_path):
    vocab_dir = tmp_path / "vocabularies"
    vocab_dir.mkdir()

    result = load_vocabulary_dataset(vocab_dir, validate=False)

    assert result == {}


def test_load_vocabulary_table_with_nulls(tmp_path):
    df = pl.DataFrame(
        {
            "concept_id": [1, 2, 3],
            "concept_name": ["Test 1", "Test 2", "Test 3"],
            "domain_id": ["Domain", "Domain", "Domain"],
            "vocabulary_id": ["Vocab", "Vocab", "Vocab"],
            "concept_class_id": ["Class", "Class", "Class"],
            "standard_concept": ["S", None, "S"],
            "concept_code": ["C1", "C2", "C3"],
            "valid_start_date": pl.Series([date(2020, 1, 1), date(2020, 1, 1), date(2020, 1, 1)]),
            "valid_end_date": pl.Series([date(2099, 12, 31), date(2099, 12, 31), date(2099, 12, 31)]),
            "invalid_reason": [None, None, "D"],
        }
    )

    csv_file = tmp_path / "CONCEPT.csv"
    df.write_csv(csv_file)

    result = load_vocabulary_table(csv_file, "concept", validate=False)

    assert result.height == 3
    assert result["standard_concept"][1] is None
    assert result["invalid_reason"][2] == "D"


def test_load_vocabulary_dataset_continues_on_error(tmp_path, sample_concepts):
    vocab_dir = tmp_path / "vocabularies"
    vocab_dir.mkdir()

    sample_concepts.write_csv(vocab_dir / "CONCEPT.csv")
    (vocab_dir / "VOCABULARY.csv").write_text("invalid,csv,content\n")

    result = load_vocabulary_dataset(vocab_dir, validate=False)

    assert "concept" in result
    assert result["concept"].height == sample_concepts.height
