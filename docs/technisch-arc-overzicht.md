# EPIC - Inrichten OMOP database op datastation

> Status: DRAFT
> Laatst bijgewerkt: 2026-02-12

## Overzicht

Elk ziekenhuisserver draait een lokale lakehouse die klinische data intern beheert en metadata/data beschikbaar stelt aan centrale services. De architectuur behandelt FHIR en OMOP als first-class uitwisselformaten met automatische registratie in de data catalog.

### Ontwerpprincipes

- **Schema-aware by default**: FHIR en OMOP zijn ingebouwd, geen bijzaak
- **Automatische lineage**: elke asset schrijft naar de DuckLake catalog, lineage via Dagster + DuckLake versioning
- **Scheiding van verantwoordelijkheden**: dlt laadt in, Dagster orkestreert, FastAPI serveert
- **Observeerbaar by default**: logging, monitoring en health checks zijn onderdeel van elk component
- **Decentraal beheerbaar**: containers worden automatisch bijgewerkt zonder centrale toegang tot nodes

### Technische Specificaties

- Controlled vocabularies nodig om OMOP te valideren → omzetten DBT naar python/duckdb
- Dagster als orchestratie, data lineage en forceert elke transformatie naar standaard I/O
- We gebruiken synthea data (FHIR, csv format) en de synthea OMOP dataset van AWS
- OMOP controlled vocabularies inclusief volledige DHD thesaurus (VT + DT)

---

## Implementatiefases

### Fase 1: Basisinfrastructuur

**Doel**: Repository, database, orchestratie en API server draaien in Docker

**Stories**:
- STORY - PLUGINLAKE - Repository opzetten met Python template en teamtoegang
- STORY - PLUGINLAKE - PostgreSQL database opzetten
- STORY - PLUGINLAKE - FastAPI server opzetten met Docker en basis API structuur
- STORY - DAGSTER - Orchestratie opzetten met Docker en PostgreSQL connectie

---

### Fase 2: Data Lakehouse

**Doel**: DuckLake operationeel met configuratie framework en generieke asset wrapper

**Stories**:
- STORY - DUCKLAKE - Basis opzetten met DuckDB en PostgreSQL connectie
- STORY - DUCKLAKE - Configuratie framework opzetten met Pydantic Settings
- STORY - DAGSTER - Generieke asset wrapper opzetten met DuckLake I/O
- STORY - DAGSTER - Assets opzetten

---

### Fase 3: OMOP Module

**Doel**: OMOP data inladen, vocabularies beschikbaar, query engine operationeel

**Stories**:
- STORY - OMOP - Inlaadmodule voor pluginlake
- STORY - OMOP - Controlled vocabularies implementeren
- STORY - OMOP - Query engine opzetten

---

### Fase 4: Data Ingestie

**Doel**: Geautomatiseerde data ingestie vanuit lokale bestanden en API endpoints

**Stories**:
- STORY - DAGSTER - Data ingestie vanuit lokale bestanden
- STORY - PLUGINLAKE - Data ingestie vanuit API endpoint

---

### Fase 5: Serving & Metadata

**Doel**: Data queryable via API, metadata inzichtelijk

**Stories**:
- STORY - PLUGINLAKE - FastAPI serve functie naar interne query engine
- STORY - DAGSTER - Metadata inzichtelijk maken via Dagster UI en DuckLake

---

### Fase 6: Monitoring & Observability

**Doel**: Functionele monitoring, health checks en alerting

**Stories**:
- STORY - PLUGINLAKE - Monitoring inrichten (functioneel)

---

### Fase 7: Deployment & CI/CD

**Doel**: Gecontaineriseerde deployment met automatische decentrale updates

**Stories**:
- STORY - PLUGINLAKE - CI/CD voor decentraal up-to-date houden van datastation containers
- STORY - PLUGINLAKE - End-to-end workflow integratie en stress test

---

## Projectstructuur

```
pluginlake/
├── configs/
│   ├── dagster/                 # dagster.yaml, workspace.yaml
│   └── pluginlake/              # App configuratie, .env.example
├── deploy/
│   ├── docker/                  # Dockerfiles
│   ├── compose/                 # Docker-compose stacks
│   ├── k8s/                     # Kubernetes manifests (later)
│   └── opentofu/                # Infra modules (later)
├── docs/
├── notebooks/
├── src/pluginlake/
│   ├── assets/                  # Asset definities (config-as-code)
│   │   ├── omop/                # OMOP assets (vocabularies, CDM tabellen)
│   │   ├── ingestion/           # Ingestie assets (bestanden, API)
│   │   └── transforms/          # Transformatie assets
│   ├── orchestration/           # Dagster infra (IO managers, resources, entry point)
│   ├── schemas/                 # OMOP/FHIR Pydantic models en DDL
│   ├── catalog/                 # DuckLake catalog beheer en metadata
│   ├── query/                   # Query engine
│   ├── sources/                 # dlt ingestie bronnen
│   ├── monitoring/              # Monitoring en alerting
│   └── api/                     # FastAPI applicatie en routes
└── tests/
    ├── unit/
    ├── integration/
    └── stress/
```

Assets (`assets/`) bevatten **wat** er moet gebeuren — welke data, welke transformatie, welke dependencies. Orchestration (`orchestration/`) bevat **hoe** Dagster het uitvoert. Assets zijn los testbaar zonder Dagster runtime.

---

## Belangrijke Beslissingen

| Beslissing | Keuze | Onderbouwing |
|------------|-------|--------------|
| OMOP opslag | Relationele tabellen | Native DuckDB schemas; vocabulary joins werken natuurlijk |
| IO manager per formaat | Ja | Schone scheiding; assets declareren formaat via `io_manager_key` |
| FastAPI los van Dagster | Ja | Verschillende scaling profielen; API stateless, Dagster stateful |
| Auth model | Placeholder nu → dataset-level ACL later | Dependency injection guard die later vervangen wordt |
| Container updates | WUD of vergelijkbaar | Decentraal; geen centrale SSH toegang nodig |
| Assets vs orchestration | Aparte modules | Assets als config-as-code los testbaar van Dagster runtime |

---

## Open Vragen

1. **Vantage6 integratie** — moet FastAPI endpoints aanbieden voor Vantage6 algoritmes, of apart houden?
2. **Centrale services** — wat pusht de lakehouse naar centraal vs. wat haalt centraal on-demand op?
3. **OMOP versie** — alleen v5.4, of ook v5.3 backwards compatibility nodig?
4. **dlt vs Dagster scheduler** — keuze voor ingestie tooling nog open
5. **FHIR module** — nog niet als stories uitgewerkt; wanneer in scope?