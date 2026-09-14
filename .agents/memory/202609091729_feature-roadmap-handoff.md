# Feature roadmap handoff

## Completed

- Inventoried 84 capabilities across core, data station, processing hub, federation, applications and assurance, plus 7 project-level items kept in a separate table so platform work is visibly separated from project work.
- Feature column follows one convention: technical term or component, then a short functional clarifier (for example `Column-level lineage (OpenLineage + Marquez): tracking tussen datasets`). Implementation detail belongs in the status column. Named tooling only where the ADRs or docs actually name it.
- Assigned each capability an implementation status, complexity and latest required phase from F0 through F5.
- Checked the roadmap against remote `main` at `3222ab9`, PR #144, `pluginlake-ehds-demo`, the ViscoSuite design, the SEIN-OMOP review, ADR-001 through ADR-009 and the HACKER second opinion.
- Corrected the roadmap model: each VM gets one configurable pluginlake deployment, projects add code locations, connectors, declarative routes and settings, and local source data remains on Data Stations.
- Added missing lanes surfaced in review: streaming ingestion (broker plus standing ingestion service, landing zone raw dump, readability gate to bronze) and non-tabular data (images, PDF, DICOM) as blobs with catalog metadata only.
- Split conflated rows: container runtime isolation vs graduated validation levels 0-4; per-result privacy checks (k-anonymity) vs cumulative SDC across queries; catalog integrity vs fail-fast validation.
- Added separate diagrams for the role-specific contents of a deployment and the standard path from one Processing Hub to multiple Data Stations; every instance has its own Nuts Node and DID.
- Clarified that the Processing Hub is the federated runtime for dispatch, aggregation, SDC and data-integrity controls; only its current implementation is still a limited prototype.
- Clarified the shared-base model: both roles use FastAPI, Dagster, Nuts and a UI, with station-specific data/enforcement components and hub-specific identity/user/access and aggregation components.

## Immediate blockers

- Complete startup conformance and project catalog namespaces within each deployment before closing F0.
- Restore project-level tests and CI lost when OMOP/FHIR code moves out of core.

## Open decisions

- OIDC provider: ADR-008 open question 11 lists Keycloak and Authentik, Zitadel is still under consideration but not yet in the ADR. M2M access is the `client_credentials` grant of that same provider, not a separate token system.
- The DuckLake IO manager is core-owned by convention only: each code location supplies its own `resources={"io_manager": ...}`, so nothing forces tabular data through the catalog. An asset wrapper that enforces this, with an explicit escape for non-tabular output, is not started.

- Decide whether federated client and dispatch responsibilities belong to pluginlake, `pluginhub` or `pluginanalytics`.
- Decide the curated and signed project-distribution model.
- Use the F2 PoC to inform the normative contract-to-compute design for F3.

## Status

Documentation only. Target files are staged for developer review; no code was committed or pushed.
