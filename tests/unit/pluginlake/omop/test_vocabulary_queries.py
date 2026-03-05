"""Tests for vocabulary query functions."""

import polars as pl

from pluginlake.omop.vocabulary_queries import (
    get_concept,
    get_concept_ancestors,
    get_concept_descendants,
    get_vocabulary_info,
    map_source_code,
    search_concepts,
)


def test_get_concept_found(test_db_with_vocabularies):
    result = get_concept(8507, con=test_db_with_vocabularies)

    assert result.height == 1
    assert result["concept_id"][0] == 8507
    assert result["concept_name"][0] == "Male"
    assert result["domain_id"][0] == "Gender"
    assert result["vocabulary_id"][0] == "Gender"


def test_get_concept_not_found(test_db_with_vocabularies):
    result = get_concept(999999, con=test_db_with_vocabularies)

    assert result.height == 0


def test_search_concepts_by_name(test_db_with_vocabularies):
    result = search_concepts("diabetes", con=test_db_with_vocabularies)

    assert result.height == 1
    assert result["concept_id"][0] == 201826
    assert "diabetes" in result["concept_name"][0].lower()


def test_search_concepts_case_insensitive(test_db_with_vocabularies):
    result = search_concepts("MALE", con=test_db_with_vocabularies)

    assert result.height >= 1
    assert 8507 in result["concept_id"].to_list()


def test_search_concepts_partial_match(test_db_with_vocabularies):
    result = search_concepts("myocard", con=test_db_with_vocabularies)

    assert result.height == 1
    assert result["concept_id"][0] == 4329847


def test_search_concepts_with_domain_filter(test_db_with_vocabularies):
    result = search_concepts("", domain_id="Gender", con=test_db_with_vocabularies, limit=100)

    assert result.height == 2
    assert all(result["domain_id"] == "Gender")
    assert set(result["concept_id"].to_list()) == {8507, 8532}


def test_search_concepts_with_vocabulary_filter(test_db_with_vocabularies):
    result = search_concepts("", vocabulary_id="SNOMED", con=test_db_with_vocabularies, limit=100)

    assert result.height >= 3
    assert all(result["vocabulary_id"] == "SNOMED")


def test_search_concepts_standard_only(test_db_with_vocabularies, sample_concepts):
    non_standard = sample_concepts.clone()
    non_standard = non_standard.with_columns(pl.lit(None).alias("standard_concept"))
    non_standard = non_standard.with_columns(pl.lit(999999).alias("concept_id"))
    non_standard = non_standard.with_columns(pl.lit("Non-standard concept").alias("concept_name"))

    result = search_concepts("non-standard", con=test_db_with_vocabularies, standard_only=True)

    assert result.height == 0


def test_search_concepts_limit(test_db_with_vocabularies):
    result = search_concepts("", limit=3, con=test_db_with_vocabularies, standard_only=False)

    assert result.height <= 3


def test_get_concept_descendants(test_db_with_vocabularies):
    result = get_concept_descendants(320128, con=test_db_with_vocabularies)

    assert result.height >= 1
    assert 4329847 in result["concept_id"].to_list()
    assert all(result["min_levels_of_separation"] >= 0)


def test_get_concept_descendants_with_max_levels(test_db_with_vocabularies):
    result = get_concept_descendants(320128, max_levels=1, con=test_db_with_vocabularies)

    assert result.height >= 1
    assert all(result["max_levels_of_separation"] <= 1)


def test_get_concept_descendants_no_descendants(test_db_with_vocabularies):
    result = get_concept_descendants(8507, con=test_db_with_vocabularies)

    assert result.height == 0


def test_get_concept_ancestors(test_db_with_vocabularies):
    result = get_concept_ancestors(4329847, con=test_db_with_vocabularies)

    assert result.height >= 2
    concept_ids = result["concept_id"].to_list()
    assert 320128 in concept_ids
    assert 201826 in concept_ids


def test_get_concept_ancestors_with_max_levels(test_db_with_vocabularies):
    result = get_concept_ancestors(4329847, max_levels=1, con=test_db_with_vocabularies)

    assert result.height >= 1
    assert all(result["max_levels_of_separation"] <= 1)


def test_get_concept_ancestors_no_ancestors(test_db_with_vocabularies):
    result = get_concept_ancestors(8507, con=test_db_with_vocabularies)

    assert result.height == 0


def test_map_source_code_icd10_to_snomed(test_db_with_vocabularies):
    result = map_source_code("E11", "ICD10CM", con=test_db_with_vocabularies)

    assert result.height == 1
    assert result["source_code"][0] == "E11"
    assert result["target_concept_id"][0] == 201826
    assert result["target_concept_name"][0] == "Type 2 diabetes mellitus"
    assert result["target_vocabulary_id"][0] == "SNOMED"


def test_map_source_code_not_found(test_db_with_vocabularies):
    result = map_source_code("INVALID", "ICD10CM", con=test_db_with_vocabularies)

    assert result.height == 0


def test_map_source_code_wrong_vocabulary(test_db_with_vocabularies):
    result = map_source_code("E11", "ICD9CM", con=test_db_with_vocabularies)

    assert result.height == 0


def test_get_vocabulary_info_all(test_db_with_vocabularies):
    result = get_vocabulary_info(con=test_db_with_vocabularies)

    assert result.height == 5
    vocab_ids = result["vocabulary_id"].to_list()
    assert "SNOMED" in vocab_ids
    assert "Gender" in vocab_ids
    assert "Race" in vocab_ids


def test_get_vocabulary_info_specific(test_db_with_vocabularies):
    result = get_vocabulary_info(vocabulary_id="SNOMED", con=test_db_with_vocabularies)

    assert result.height == 1
    assert result["vocabulary_id"][0] == "SNOMED"
    assert result["vocabulary_name"][0] == "SNOMED CT"
    assert result["vocabulary_reference"][0] == "http://www.snomed.org/"


def test_get_vocabulary_info_not_found(test_db_with_vocabularies):
    result = get_vocabulary_info(vocabulary_id="INVALID", con=test_db_with_vocabularies)

    assert result.height == 0


def test_multiple_queries_same_connection(test_db_with_vocabularies):
    result1 = get_concept(8507, con=test_db_with_vocabularies)
    result2 = search_concepts("diabetes", con=test_db_with_vocabularies)
    result3 = get_vocabulary_info(con=test_db_with_vocabularies)

    assert result1.height == 1
    assert result2.height == 1
    assert result3.height == 5
