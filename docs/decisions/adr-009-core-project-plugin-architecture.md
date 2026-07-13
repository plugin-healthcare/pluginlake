# ADR-009: Core platform, projects, and the plugin conformance model

- **Status:** Proposed
- **Date:** 2026-07-09
- **Authors:** Yannick Vinkesteijn

## TL;DR

`pluginlake` becomes pure core infrastructure: the storage engine (DuckLake), the Dagster runtime, the API gateway (the perimeter), the CLI, and the deploy stack.
All domain-specific code moves into separate installable packages called **projects**, starting with the EHDS demo.

This ADR draws one line precisely, because we kept blurring it: a **project** and a **federation** are two different things on two different axes.

- A **project** is a reusable capability unit: a specific set of datasets/sources, some pipeline implementations, and its config.
  Nothing more.
  It carries no governance, no contracts, no permits.
  A project maps to one DuckLake catalog and one asset-URN namespace.
- A **federation/collaboration** (defined in [ADR-006](adr-006-nuts-node-decentralized-auth.md) and [ADR-008](adr-008-dataspace-protocol-authz-authc-rbac.md)) is the governance and access unit: the organizations, contracts, and per-user permits that decide who may do what with which data.

The two are orthogonal and relate many-to-many.
A federation can span multiple projects, and a project can serve multiple federations.
They connect through contracts and ODRL permits that reference a project's asset URNs and operations.
This is what lets pipelines and data be reused across federations without duplicating anything: data is materialized once in the project catalog, and each federation is granted access to it (or a subset) through its own contract.

Projects plug into the core through a versioned plugin contract.
Because the network is federated and no node can be centrally forced, standardization is enforced bottom-up: a machine-checkable conformance suite plus validation gates at build, publish, install, and runtime, and every node re-verifies the contract on what it receives, not only on what it ships.

Authentication, authorization, permits, and query safety are out of scope here.
They live in the ADR-006/008 family (see "Scope boundary and ADR numbering" below).

## Context

Today OMOP/FHIR domain code is woven through four layers of the core package:

1. Dagster code locations: `assets/*`, `definitions/omop.py`, `definitions/fhir.py`
2. Domain toolkits: `omop/`, `fhir/`
3. API: `api/routers/{omop,omop_statistics,fhir,fhir_statistics}.py`, with hardcoded router includes in `api/app.py`
4. UI: `src/pluginlake-ui/datastation` OMOP/FHIR pages and backends

This makes `pluginlake` a healthcare-demo application rather than a reusable platform.
We want `pluginlake` to be infrastructure that many projects deploy onto, and we want other organizations to be able to build their own projects (datasets, sources, pipelines) and deploy them on their own data station or processing hub, while the platform stays standardized across the network.

Three prior decisions constrain how we do this:

- **ADR-004 already owns the schema slot.** The first segment of a Dagster asset key is the DuckLake schema, and that schema is the medallion processing layer (`staging`, `raw`, `curated`, `reference`, `aggregated`). DuckDB is limited to three levels (`catalog.schema.table`) with no nesting. ADR-004 also states there is no per-station schema mapping so every station speaks the same language. A per-project schema is therefore impossible: the schema level is taken by the layer, and there is no free level.
- **ADR-006 keeps Nuts coarse.** Nuts handles node-to-node machine membership and coarse roles (`hub`, `station`) only. It decides which machines a station will talk to. It does not carry project or dataset scope.
- **ADR-008 owns access.** Source access is granted by a bilateral DSP contract between a processing hub and a data station. Per-user rights are carried by the ODRL-based PluginlakeAccessCredential. Different hubs and users get different access to the same data through different contracts and permits.

## Decision

Split the codebase into a core platform package and one package per project, and define the project unit, its naming, and the conformance model.

### 1. Two axes: project (capability) and federation (access)

| Axis | Unit | Owns | Defined in |
|---|---|---|---|
| Capability / deployment | **Project** | datasets/sources, pipeline implementations, config, canonical schema | this ADR |
| Governance / access | **Federation / collaboration** | organizations, contracts (DSP), permits (ODRL), SDC | ADR-006, ADR-008 |

They are orthogonal and many-to-many:

- A federation can span multiple projects (an oncology collaboration grants access to an OMOP project and an imaging project).
- A project can serve multiple federations (a station shares its OMOP catalog with two collaborations under different contracts, with separate SDC per federation).

A federation's contract enumerates which datasets (project asset URNs) and which operations (predefined queries, approved algorithms) it grants.
The project itself is governance-agnostic and knows nothing about federations.

Consequences of this split that we accept:

- **Reuse without duplication.** Data is materialized once per project catalog; federations reference it. Pipelines live in the project; any federation using the project reuses them.
- **A reused project is a shared dependency.** Changing a project affects every federation that depends on it (a diamond dependency). Projects are versioned, federations pin the version they depend on, and upgrades must be compatible or coordinated.
- **Privacy stays federation-side.** SDC and permits are applied per federation at the hub, never inside the project, precisely so the project stays reusable.

### 2. Project maps to a DuckLake catalog, not a schema

A project is one **DuckLake catalog** (a separate `ATTACH`), not a schema.
This preserves ADR-004 unchanged inside each project: the schema stays the medallion layer.

```
{project_catalog} . {layer_schema} . {domain}_{table}
   ehds_demo       .    curated     .  omop_condition_era
```

Rationale:

- The schema level is already the layer (ADR-004), and DuckDB has no free fourth level. The catalog level is the only place a project can live.
- Each project catalog has its own PostgreSQL metadata namespace and its own `DATA_PATH` prefix, giving clean storage isolation and per-project retention and backup.
- A node attaches only the catalogs for the projects it has installed, which matches multi-project stations naturally.
- The catalog boundary maps directly to the project's asset-URN namespace used by ODRL in ADR-008.

The lighter alternative, a project as a table-name prefix within existing layers (`curated.ehdsdemo_omop_condition_era`), is rejected: weaker isolation (per table, not per catalog) and messier ODRL grants.

The current code attaches a single catalog as `ducklake`.
Multi-project generalizes this to one attach per installed project (see migration in open questions).

### 3. One project id threads through every existing naming convention

A project has a single id: a kebab-case slug (for example `ehds-demo`), normalized to a valid catalog identifier (`ehds_demo`) and an env prefix (`EHDS_DEMO`).

| Concern | Existing convention | Project-linked form |
|---|---|---|
| Storage isolation | schema = layer (ADR-004) | **catalog = project**; layer stays the schema |
| Table name | `{domain}_{table}` (ADR-004) | unchanged, inside the project catalog |
| Asset key | `[layer, domain, table]` (ADR-004) | unchanged; the code location binds to its project catalog |
| DATA_PATH | `DATA_PATH/{schema}/{table}/` (ADR-004) | `DATA_PATH/{project}/{schema}/{table}/` |
| ODRL asset URN | `urn:pluginlake:dataset:{name}` (ADR-008) | `urn:pluginlake:{project}:dataset:{layer}:{table}` |
| DSP contract scope | per federation (ADR-008) | contract references project asset URNs |
| Code location | `pluginlake.definitions.*` (ADR-006) | one code location per project |
| Config | env-prefixed Settings | prefix `PLUGINLAKE_{PROJECT}_...` |
| Asset/operation registry | per-station YAML (ADR-008) | keyed by project |

### 4. What a project contributes

A project is a package that depends on `pluginlake` and exposes one entry point in the group `pluginlake.projects`, returning a validated `ProjectManifest`.
The manifest declares:

- the project id, catalog name, asset-URN namespace, and config prefix
- the Dagster code location module (assets, jobs, sensors) for ingestion and transforms
- framework-agnostic **data connectors** (see below)
- registered **datasets, predefined queries, and operations**: the machine-readable capabilities the platform exposes and a federation may grant
- declarative **UI page and router specs** for the local operator plane, in the standard machine-understandable form (configuration, not arbitrary code)
- its own Pydantic Settings with the project env prefix
- the required core version range (`requires pluginlake >=X,<Y`)

**Two planes.**
The federated external plane (DSP plus ODRL, ADR-008) is what other stations and hubs query.
It stays uniform, and a project adds capability there only as registered operations and predefined queries, never as new external endpoints.
The local operator plane is the datastation's own UI and its backing endpoints, used by local staff behind the perimeter.
It is project-specific but declared, not hand-coded.

**Declared, not coded.**
Routers and UI pages ship as standardized configuration in the manifest, so they are machine-understandable and validated by the conformance suite.
Core interprets the spec and mounts or renders it uniformly.
The spec includes placement (where a page appears in the UI navigation, where a route registers), but placement is data, not power: it is validated to stay within the project's namespace and plane, to pass the perimeter (PEP), and it cannot alter or escape the authn, authz, or scope model.
Non-conformant placement (unauthenticated, wrong plane, outside the namespace, or colliding with core or another project) is rejected.
A governed code escape hatch exists for rare custom components (for example bespoke charts), still packaged conformantly.
This keeps arbitrary code out of the gateway and removes the dependency and process-isolation risk of third-party router code.

**Few endpoints, precise permits.**
The API is a small fixed set in two kinds:

- **Overview and introspection endpoints**: what datasets exist in this station, what operations or compute a hub offers. Self-describing and machine-readable. On the federated plane this is the DSP Catalog (DCAT plus ODRL offers); core derives it from the manifest and the catalog, so a project declares its datasets and operations and the overview is generated, not written.
- **Scoped operation endpoints**: request specific data or compute.

Precision comes from the permit, not the URL space.
The ODRL permit in the Verifiable Credential (ADR-008) carries the exact scope (action, asset URN, columns, row filters, constraints), so there is no need to mint many specific endpoints.
A bespoke path like `/omop/statistics` becomes a registered operation invoked through the uniform scoped endpoint and selected by the permit or operation id, with a declarative page that renders it.

### 5. Data connectors are framework-agnostic, below Dagster

A connection to a data source (credentials, location, extensions) is defined in the shared config and backend layer, not inside a Dagster resource.
Connectors generalize the existing `StorageBackend` contract (`configure_duckdb(conn)` plus a namespace/path) and are declared in project config.

This keeps the read path independent of Dagster:

- Data access goes through the DuckLake catalog via DuckDB and never triggers a Dagster job.
- Dagster code locations define ingestion and transforms (the write side) only.
- Both Dagster (for ingestion) and the standardized query engine (for reads) consume the same connector.

If a source needs arbitrary Python (for example an ODBC driver or a REST client), it is **ingest-only** through Dagster, which is isolated in its own code-location server.
Connectors loaded into the core query-engine process are restricted to DuckDB-native capabilities (S3, Azure, HTTP, Parquet, secrets), so one project cannot destabilize the shared read path.
The federated interface serves only lake-resident conformed data; query-in-place of an external source is a local convenience or a pipeline input, never the federated surface.

### 6. Ingestion tiers and the source-to-canonical seam

A project standardizes everything from its canonical schema onward, but hospitals have heterogeneous source systems, so the mapping into the canonical schema cannot be fully standardized.

- **Tier 1, source to canonical (site-specific):** local source connection plus the mapping into the project's canonical input contract. This is the irreducible per-node part.
- **Tier 2, canonical to products (project-standard):** transforms, aggregates, and predefined queries. Identical on every node running the project.

The project defines and validates a canonical input contract at the Tier1/Tier2 boundary, so Tier 2 standardization does not silently depend on each site's mapping.
How Tier 1 is provided is an open question (see below).

### 7. Standardization is enforced bottom-up, and verified at every boundary

Because the network is federated and sovereign, no node can be centrally forced to conform.
Standardization is therefore enforced by a versioned contract plus mechanical validation, applied at multiple gates.

- **Versioned plugin contract.** Core owns base classes, the Pydantic `ProjectManifest`, and the `pluginlake.projects` entry-point group, with a declared core version. Projects build against it.
- **Conformance suite.** Core ships `pluginlake verify`. A package is a valid project only if it passes: manifest validates, catalog and URN namespace are unique and present, connectors implement the base contract, the project writes only inside its own catalog, predefined queries register correctly, config loads. This mirrors the DSP TCK already referenced in ADR-008.
- **Four gates, fail fast:**
  1. Build/CI: the conformance suite must pass.
  2. Publish: the manifest is validated and the package is signed.
  3. Install/load at a node: core validates the manifest against the running platform version, checks namespace uniqueness, schema and URN conformance, that config loads, and that declared page and route placement stays within the project namespace and plane and passes the PEP. Reject on mismatch, at deploy time, not at request time.
  4. Runtime (PEP): even a loaded project cannot bypass authn/authz or write outside its catalog. The perimeter, catalog isolation, and ODRL contain it.
- **Verify at every boundary (trust no node).** A sovereign node could run a modified core that skips its own gates, so federation safety does not rely on a node self-enforcing what it ships. Each node re-verifies the contract, capability, and pinned version on what it receives, at enrollment and per request. A version mismatch excludes the node from that federation's queries; it never silently returns wrong results.
- **Golden-path tooling.** The CLI (`pluginlake init <name>`) and the project template scaffold a project that passes conformance by default, so conforming is easier than not.
- **Governed distribution.** No station installs arbitrary internet code. Projects are curated, reviewed, and signed under network governance, and a station operator chooses which vetted projects to install.

### Scope boundary and ADR numbering

This ADR decides platform-versus-project packaging, the project unit, its naming, connectors, and the conformance model.
It deliberately does not decide authentication, authorization, permits, contract-to-compute mapping, or query safety.

ADR-008 defers several items to "ADR-009": the PluginlakeAccessCredential schema, contract-to-compute mapping, structured filter AST, the pre-approved algorithm and container registry, privacy validation for non-aggregate queries, and techniques to limit data-exfiltrating operations.
Those are authorization and query-safety concerns, not packaging concerns.
They should live in a dedicated ADR in the 006/008 family.
Open question: renumber this packaging ADR, or add the authz/query-safety ADR under a new number and update the ADR-008 references, so the two topics stay in separate, coherent documents.

## Architecture

```
   Capability axis (this ADR)                 Governance axis (ADR-006/008)

   ┌───────────────────────────┐              ┌───────────────────────────┐
   │ project: omop-core        │              │ federation: oncology      │
   │  catalog + URN namespace  │◄────grants───│  hub + contracts + permits│
   │  datasets, pipelines,     │              │  SDC per federation       │
   │  predefined queries       │◄──┐          └───────────────────────────┘
   └───────────────────────────┘   │ grants
   ┌───────────────────────────┐   │          ┌───────────────────────────┐
   │ project: imaging          │◄──┴──────────│ federation: quality       │
   └───────────────────────────┘   ▲          └───────────────────────────┘
                                    │
                       many-to-many via contracts/ODRL URNs
```

```
                       ┌──────────────────────────────────────┐
                       │            pluginlake (core)          │
   external clients    │   ┌───────────────┐   ┌───────────┐  │
   ───────────────────▶│   │ API gateway   │   │  Dagster  │  │
                       │   │ (perimeter,   │   │  runtime  │  │
                       │   │  uniform      │   │ (code     │  │
                       │   │  endpoints,   │   │  locations│  │
                       │   │  ODRL-scoped) │   │  isolated)│  │
                       │   └──────┬────────┘   └─────┬─────┘  │
                       │          │ reads (no job)   │ writes │
                       │   ┌──────▼──────────────────▼──────┐ │
                       │   │      DuckLake storage engine     │ │
                       │   │   catalog-per-project isolation  │ │
                       │   └──────────────────────────────────┘ │
                       │      ▲ pluginlake.projects entry point  │
                       └──────┼─────────────────┼───────────────┘
                       ┌──────┴─────┐     ┌──────┴─────────────┐
                       │ project    │     │ project            │
                       │ omop-core  │     │ ehds-demo          │
                       │ manifest,  │     │ manifest,          │
                       │ code loc,  │     │ code loc,          │
                       │ connectors,│     │ connectors,        │
                       │ queries    │     │ queries            │
                       └────────────┘     └────────────────────┘
```

## How deployment and reuse work

Deployment separates two concerns: provisioning the platform, and configuring which projects a node runs.
The platform (core package plus the deployable stack: compose, docker, infra) is provisioned once and is identical everywhere.
What a given node offers is then a matter of configuration, not of rebuilding core.

**Declarative node configuration.**
Each node has a deployment descriptor that lists the enabled projects and the version pinned for each.
This descriptor is the single source of truth for what the node offers, and it is the only thing an operator edits to change that.
Enabling a project is adding an entry; removing one is deleting an entry.

**Reconcile through a verification gate.**
Applying the descriptor is a reconcile step: core installs the vetted project package(s), runs the conformance and version-compatibility checks (section 7), attaches each project's catalog, generates the Dagster code-location workspace from the manifests, and restarts the affected services.
Verification happens at apply time, not at request time: a project that fails conformance or targets an incompatible core version is rejected before it can serve.
Because storage, config, and asset URNs are namespaced per project (sections 2 and 3), enabled projects coexist without collisions, and add or remove is a descriptor edit followed by re-apply, with no changes to core.

**Deployment is not access.**
Enabling a project makes its capability present on the node; it does not grant anyone the right to use it.
A federation separately grants a hub access to a project's datasets and operations through DSP contracts and ODRL permits (ADR-008).
The same enabled project can be granted to several federations without duplication, which is what makes reuse across federations possible.

**Doors kept open.**
The descriptor is a local list today; it can later be backed by a registry of vetted, signed projects that operators pick from.
Reconcile is install-and-restart today; per-project isolation, hot reload, and stronger supply-chain gates can be layered onto the same descriptor and verification model without changing the contract.

## Rollout phases

1. **Extension points in core (non-breaking).** Add the `pluginlake.projects` entry point, the `ProjectManifest`, and catalog-per-project attach. Register the existing OMOP/FHIR components through the new mechanism while they still live in-tree, so behaviour is unchanged.
2. **CLI, template, and conformance suite.** Provide `pluginlake init`, the project template, shared base classes (Settings, connectors), the manifest model, and `pluginlake verify`, so projects can be created, validated, and deployed on the same stack.
3. **Extract the EHDS demo.** Create `pluginlake-ehds-demo` from the template; move the domain layers, example data, and notebooks; wire them via the manifest; depend on `pluginlake`.
4. **Slim the core.** Remove domain code from `pluginlake`; the core ships uniform endpoints only. Update deploy templates to install project packages and list code locations.
5. **Docs, CI, tests, changelog.** Split tests, update guides, validate end-to-end with `compose up` and the demo installed.

## Consequences

- `pluginlake` becomes a reusable platform; projects are self-contained, independently versioned, and reusable across federations without duplicating data or pipelines.
- Catalog-per-project isolation aligns storage with the ODRL asset-URN namespaces and keeps ADR-004's schema-equals-layer convention intact.
- One perimeter is preserved. The federated surface stays uniform, and the local operator plane is project-specific but declared as machine-understandable config, not arbitrary code, so little bespoke code reaches the gateway.
- A small fixed set of endpoints (overview and scoped) plus permit-carried precision avoids endpoint proliferation and keeps the ODRL/SDC surface intact.
- The read path is Dagster-independent, so the orchestrator can be replaced or bypassed for reads without affecting data access.
- A reused project is a shared dependency, so version pinning and compatibility policy across dependent federations become an operational obligation.
- Bottom-up standardization plus verify-at-every-boundary means non-conformance is detected and rejected at trust boundaries, not silently tolerated, so nodes do not drift and detach.
- Cost: a versioned plugin contract and conformance suite to maintain, cross-repo coordination, governed distribution, and a migration to move the demo out and split the single catalog.

## Open questions

1. **Tier 1 source-to-canonical seam.** Project-shipped connectors and mappings for known source systems, or a project-defined canonical input contract plus site-written adapters?
2. **Contract scope.** Confirm that DSP contracts are project-scoped (one agreement per project/federation at a station), to keep storage, ODRL, and SDC boundaries on the same seam.
3. **ADR numbering.** Resolve the collision: ADR-008 defers authz and query-safety to "ADR-009", but this ADR is packaging. Renumber, or add the authz/query-safety ADR under a new number and update references.
4. **Shared-project versioning.** Compatibility policy when a project is a shared dependency of multiple federations (pin range versus latest, coordinated upgrades).
5. **Migration.** Path for existing data written under the current single-catalog layout to catalog-per-project.
6. **Cross-project reuse.** Whether a shared base library of connectors and assets (reuse across projects, not only across federations) becomes its own unit later, layered on the same contract.
