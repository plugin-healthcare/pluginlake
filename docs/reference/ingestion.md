# Ingestion Services

The core gateway ships a generic, project-agnostic ingestion service. Domain
specific formats (OMOP CSV, FHIR NDJSON, and so on) are contributed by project
packages and documented alongside their own code — see the project's reference
docs (for example, the `pluginlake-ehds-demo` project).

## Generic Ingestion

::: pluginlake.api.services.ingestion
