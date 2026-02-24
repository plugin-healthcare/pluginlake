# OMOP Controlled Vocabularies

The pluginlake OMOP module includes support for OMOP controlled vocabularies (also called standardized vocabularies). These vocabularies provide standard concepts for clinical data and enable:

- Validation of concept IDs in clinical data against standard terminologies
- Mapping from source codes (ICD10, ICD9, etc.) to standard concepts
- Hierarchy traversal and concept relationships
- Standardized terminology across heterogeneous data sources

## Overview

OMOP vocabularies consist of 10 core tables:

- **CONCEPT** - All standard and source concepts from multiple vocabularies
- **VOCABULARY** - Metadata about vocabulary sources (SNOMED, LOINC, RxNorm, etc.)
- **DOMAIN** - Clinical domains (Condition, Drug, Measurement, etc.)
- **CONCEPT_CLASS** - Classifications within vocabularies
- **CONCEPT_RELATIONSHIP** - Relationships between concepts
- **RELATIONSHIP** - Relationship type definitions
- **CONCEPT_SYNONYM** - Alternative names for concepts
- **CONCEPT_ANCESTOR** - Pre-computed hierarchical relationships
- **SOURCE_TO_CONCEPT_MAP** - Mappings from source codes to standard concepts
- **DRUG_STRENGTH** - Drug ingredient and strength information

## Download Vocabularies from ATHENA

OMOP vocabularies are distributed through ATHENA (https://athena.ohdsi.org). Currently, manual download is required:

1. Create an account at https://athena.ohdsi.org
2. Log in and select desired vocabularies:
   - **Minimum recommended**: SNOMED, LOINC, RxNorm, ICD10CM
   - Additional vocabularies as needed for your data
3. Download the vocabulary bundle ZIP file
4. Extract to the configured vocabulary directory

## Configuration

Vocabulary settings can be configured via environment variables or the `OMOPSettings` class:

```python
from pluginlake.omop.config import get_omop_settings

settings = get_omop_settings()

settings.vocabulary_dir          # Path("data/omop_vocabularies")
settings.vocabulary_schema        # "omop_vocab"
settings.vocabulary_auto_load     # True
```

### Environment Variables

```bash
export OMOP_VOCABULARY_DIR="data/omop_vocabularies"
export OMOP_VOCABULARY_SCHEMA="omop_vocab"
export OMOP_VOCABULARY_AUTO_LOAD="true"
```

## Loading Vocabularies

### Manual Loading

Load vocabulary files explicitly:

```python
from pathlib import Path
from pluginlake.omop.loader import load_vocabulary_dataset
from pluginlake.omop.storage import save_vocabulary_table

vocab_dir = Path("data/omop_vocabularies")
vocab_tables = load_vocabulary_dataset(vocab_dir)

for table_name, df in vocab_tables.items():
    print(f"Loaded {table_name}: {len(df):,} rows")
    save_vocabulary_table(df, table_name)
```

### Automatic Loading

Vocabularies are automatically loaded when first accessed via query functions:

```python
from pluginlake.omop.vocabulary_queries import get_concept

concept = get_concept(8507)
print(concept["concept_name"][0])
```

## Querying Vocabularies

### Get Concept by ID

```python
from pluginlake.omop.vocabulary_queries import get_concept

concept = get_concept(8507)

print(f"Concept ID: {concept['concept_id'][0]}")
print(f"Name: {concept['concept_name'][0]}")
print(f"Domain: {concept['domain_id'][0]}")
print(f"Vocabulary: {concept['vocabulary_id'][0]}")
```

### Search Concepts

```python
from pluginlake.omop.vocabulary_queries import search_concepts

concepts = search_concepts("diabetes", domain_id="Condition", limit=10)

for row in concepts.iter_rows(named=True):
    print(f"{row['concept_id']}: {row['concept_name']}")
```

### Map Source Code to Standard Concept

```python
from pluginlake.omop.vocabulary_queries import map_source_code

mapping = map_source_code("E11", "ICD10CM")

if mapping.height > 0:
    print(f"ICD10CM E11 maps to:")
    print(f"  Concept ID: {mapping['target_concept_id'][0]}")
    print(f"  Name: {mapping['target_concept_name'][0]}")
    print(f"  Vocabulary: {mapping['target_vocabulary_id'][0]}")
```

### Traverse Hierarchies

Get descendants (children) of a concept:

```python
from pluginlake.omop.vocabulary_queries import get_concept_descendants

descendants = get_concept_descendants(320128, max_levels=2)

for row in descendants.iter_rows(named=True):
    indent = "  " * row['min_levels_of_separation']
    print(f"{indent}{row['concept_name']} ({row['concept_id']})")
```

Get ancestors (parents) of a concept:

```python
from pluginlake.omop.vocabulary_queries import get_concept_ancestors

ancestors = get_concept_ancestors(4329847)

for row in ancestors.iter_rows(named=True):
    print(f"Level {row['min_levels_of_separation']}: {row['concept_name']}")
```

## Validating Clinical Data

### Validate Concept IDs

```python
from pluginlake.omop.vocabulary_validation import validate_concept_ids
from pluginlake.omop.storage import get_duckdb_connection

con = get_duckdb_connection()

concept_ids = [8507, 8532, 999999]
results = validate_concept_ids(con, concept_ids)

invalid = results.filter(~results["is_valid"])
for row in invalid.iter_rows(named=True):
    print(f"Concept {row['concept_id']}: {row['validation_message']}")
```

### Validate All Concepts in a Table

```python
from pluginlake.omop.vocabulary_validation import validate_table_concepts
from pluginlake.omop.storage import get_duckdb_connection
import polars as pl

con = get_duckdb_connection()

condition_data = pl.DataFrame({
    "condition_occurrence_id": [1, 2, 3],
    "person_id": [1, 2, 3],
    "condition_concept_id": [201826, 320128, 999999],
    "condition_type_concept_id": [38000280, 38000280, 38000280],
})

validation_results = validate_table_concepts(
    con, condition_data, "condition_occurrence"
)

invalid = validation_results.filter(~validation_results["is_valid"])
print(f"Found {len(invalid)} invalid concepts")
```

### Validation with Filters

Validate concepts belong to specific domain or vocabulary:

```python
from pluginlake.omop.vocabulary_validation import validate_concept_ids

results = validate_concept_ids(
    con,
    [201826, 320128],
    domain_id="Condition",
    vocabulary_id="SNOMED",
    standard_only=True
)
```

## Performance Considerations

### Large Vocabulary Tables

Vocabulary tables can be very large:

- **CONCEPT**: 500,000+ rows
- **CONCEPT_RELATIONSHIP**: 10,000,000+ rows
- **CONCEPT_ANCESTOR**: 50,000,000+ rows

The module uses several strategies for performance:

1. **Parquet storage** with ZSTD compression (80-90% size reduction)
2. **DuckDB views** for zero-copy queries
3. **Lazy loading** - vocabularies only loaded when first accessed
4. **Indexed queries** - DuckDB automatically optimizes commonly-used filters

### Connection Reuse

Reuse connections for multiple queries to avoid repeated vocabulary loading:

```python
from pluginlake.omop.storage import get_duckdb_connection, register_vocabulary_tables
from pluginlake.omop.vocabulary_queries import get_concept, search_concepts

con = get_duckdb_connection()
register_vocabulary_tables(con)

concept1 = get_concept(8507, con=con)
concept2 = get_concept(8532, con=con)
results = search_concepts("hypertension", con=con)

con.close()
```

## File Formats

### Supported Input Formats

- **CSV** - Comma-separated (Excel, custom exports)
- **TSV** - Tab-separated (ATHENA standard)

The loader automatically detects separator format.

### Storage Format

Vocabularies are converted to **Parquet** format with ZSTD compression for optimal storage and query performance:

```
data/omop_vocabularies/
├── CONCEPT.csv           # Source files from ATHENA
├── VOCABULARY.csv
├── ...
└── parquet/              # Converted Parquet files
    ├── concept.parquet
    ├── vocabulary.parquet
    └── ...
```

## Troubleshooting

### Vocabularies Not Found

If vocabularies fail to load:

1. Check the configured vocabulary directory exists:

   ```python
   from pluginlake.omop.config import get_omop_settings
   settings = get_omop_settings()
   print(settings.vocabulary_dir)
   ```

2. Verify required files exist:

   ```bash
   ls data/omop_vocabularies/
   ```

3. Check logs for detailed error messages:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

### Missing Concepts

If concept lookups return empty results:

1. Verify vocabulary files were loaded:

   ```python
   from pluginlake.omop.vocabulary_queries import get_vocabulary_info
   vocabularies = get_vocabulary_info()
   print(vocabularies)
   ```

2. Check concept exists in source files:

   ```bash
   grep "8507" data/omop_vocabularies/CONCEPT.csv
   ```

3. Verify vocabulary schema is registered:
   ```python
   con.execute("SHOW TABLES FROM omop_vocab").fetchall()
   ```

### Slow Queries

If queries are slow:

1. Ensure Parquet files are generated (first-time conversion can be slow)
2. Use connection reuse pattern (see Performance section)
3. Add filters to queries (domain_id, vocabulary_id) to reduce result sets
4. Consider indexing frequently-queried columns in DuckDB

## API Reference

### Query Functions

All query functions in `pluginlake.omop.vocabulary_queries`:

- `get_concept(concept_id, ...)` - Retrieve single concept details
- `search_concepts(term, ...)` - Search concepts by name
- `get_concept_descendants(ancestor_concept_id, ...)` - Get hierarchy descendants
- `get_concept_ancestors(descendant_concept_id, ...)` - Get hierarchy ancestors
- `map_source_code(source_code, source_vocabulary_id, ...)` - Map source to standard
- `get_vocabulary_info(vocabulary_id=None, ...)` - Get vocabulary metadata

### Validation Functions

All validation functions in `pluginlake.omop.vocabulary_validation`:

- `validate_concept_ids(conn, concept_ids, ...)` - Validate list of concept IDs
- `validate_table_concepts(conn, df, table_name, ...)` - Validate all concepts in table

### Loader Functions

All loader functions in `pluginlake.omop.loader`:

- `load_vocabulary_table(file_path, table_name, ...)` - Load single vocabulary file
- `load_vocabulary_dataset(data_dir, ...)` - Load all vocabulary files

### Storage Functions

Storage functions in `pluginlake.omop.storage`:

- `save_vocabulary_table(df, table_name, ...)` - Save vocabulary as Parquet
- `register_vocabulary_tables(con, ...)` - Register vocabularies in DuckDB

## Best Practices

1. **Download comprehensive vocabularies** - Include SNOMED, LOINC, RxNorm, ICD10CM at minimum
2. **Validate early** - Check concepts during ETL, not at query time
3. **Use standard concepts** - Prefer standard_concept='S' for analytics
4. **Map source codes** - Use SOURCE_TO_CONCEPT_MAP for code standardization
5. **Leverage hierarchies** - Use CONCEPT_ANCESTOR for cohort expansion
6. **Reuse connections** - Avoid repeated vocabulary loading
7. **Monitor vocabulary versions** - Update vocabularies periodically from ATHENA

## See Also

- [OMOP Module Documentation](README.md)
- [OMOP CDM Specification](https://ohdsi.github.io/CommonDataModel/)
- [ATHENA Vocabulary](https://athena.ohdsi.org)
- [OHDSI Documentation](https://ohdsi.github.io)
