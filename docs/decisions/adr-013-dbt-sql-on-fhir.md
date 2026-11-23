# ADR-013: dbt and SQL on FHIR in project pipelines

- **Status:** Proposed
- **Date:** 2026-11-19

## Context

FHIR resources can contain nested and repeating elements, while analysts often work with tables.
[SQL on FHIR](https://sql-on-fhir.org/ig/) lets a project describe a tabular projection of one resource type in a `ViewDefinition`, using FHIRPath to select fields and define rows.
[dbt](https://docs.getdbt.com/docs/build/sql-models) serves a different purpose: it lets a project express transformations over tables in SQL.
A project could use either tool on its own.

## Proposal

Evaluate both tools in one project before deciding whether pluginlake needs shared support for either.
Keep the view definition and dbt model with the project, consistent with [ADR-009](adr-009-core-project-plugin-architecture.md).
The alternative is to implement the same transformation as an ordinary Dagster asset using DuckDB or Polars, which needs no additional runner.
The reason to try SQL on FHIR is to reuse a standard projection; the reason to try dbt is to let analysts maintain the downstream model as SQL.

For the trial, use a SQL on FHIR runner to project synthetic `Patient` resources into a DuckLake table with one row per patient and a `birth_year` column derived from `Patient.birthDate`.
Have Dagster run a dbt model that reads that table and counts patients by birth year.
The trial succeeds at dataset level if Marquez shows one path from the registered FHIR input through the projection to the count table.
The projection must have the same catalog identity when the runner writes it and when dbt reads it.
Run the same Dagster job twice against the same target without resetting the catalog.
With unchanged input, the second run must produce the same counts, preserve upstream tables and appear as a new run of the same job in Marquez.

## Questions for the trial

- What does `dagster-dbt` provide with a standard DuckLake profile? Try it without a pluginlake wrapper first and record any gaps before considering one.
- Which runner can execute the view on the station's FHIR data, and how should it represent missing or partial birth dates?
- Should the dbt DuckDB profile attach DuckLake directly, or should pluginlake supply the attachment? Compare how each handles replacing an existing relation on the second run, including whether the adapter issues an unsupported `DROP ... CASCADE`.
- Which dbt materializations and incremental strategies match the station's write modes? Start with the one used by the trial and leave the others undecided.
- Which catalog permissions and storage credentials does each step need to read its inputs and write only its own outputs?
- Can the [OpenLineage dbt integration](https://openlineage.io/docs/integrations/dbt/) link the model to its Dagster run without duplicate jobs or datasets in Marquez?
- Which field mappings can we verify on each side of the projection? For example, can we trace the model's `birth_year` to the projection column, and separately trace that column to `Patient.birthDate`?

Column names and types alone are not evidence of column lineage.
Record any missing mapping explicitly before deciding whether to extend the [column-level lineage strategy](adr-007-column-level-lineage.md).
