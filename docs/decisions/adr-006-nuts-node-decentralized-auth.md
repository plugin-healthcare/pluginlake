# ADR-006: Nuts Node for decentralized authentication and authorization

**Status:** Proposed
**Date:** 2026-03-19

## Context

pluginlake is a federated data lakehouse where each hospital runs its own data station.
Stations need to exchange data and query each other's APIs (see [ADR-005](adr-005-fastapi-gateway.md)) without relying on a single central identity provider.

The FastAPI gateway currently has placeholder auth ([security.py](../../src/pluginlake/api/security.py) returns an anonymous user for every request).
We need a solution that:

- Authenticates requests between stations without a central auth server.
- Authorizes access to specific data per organization.
- Provides an audit trail for healthcare compliance (NEN 7510, AVG/GDPR).
- Fits the federated model where each station is sovereign over its own data.

[Nuts Node](https://nuts-node.readthedocs.io/en/v5.4/) is an open-source, Dutch healthcare-specific infrastructure component that provides decentralized identity, authentication, and authorization using W3C standards.

## Decision

**Adopt Nuts Node as the decentralized auth layer for inter-station communication, integrated as FastAPI middleware.**

### Architecture

```
Data user (org)          Processing Hub (role: Processing Hub)                      Datastation (role: datastation)
                    ┌──────────────────────┐                 ┌──────────────────────┐
  Nuts or OIDC      │  pluginlake API      │                 │  pluginlake API      │
  (org-verified)    │  ┌────────────────┐  │   Nuts JWT      │  ┌────────────────┐  │
 ──────────────────►│  │  FastAPI       │  │  (purposeOfUse) │  │  FastAPI       │  │
                    │  │  gateway       │◄─┼────────────────►│  │  gateway       │  │
                    │  │  ┌───────────┐ │  │                 │  │  ┌───────────┐ │  │
                    │  │  │ Nuts auth │ │  │                 │  │  │ Nuts auth │ │  │
                    │  │  │ middleware│ │  │                 │  │  │ middleware│ │  │
                    │  │  └───────────┘ │  │                 │  │  └───────────┘ │  │
                    │  │  + SDC assets  │  │                 │  │  + query assets│  │
                    │  └────────────────┘  │                 │  └────────────────┘  │
                    │                      │                 │                      │
                    │  ┌────────────────┐  │  gRPC (mTLS)    │  ┌────────────────┐  │
                    │  │  Nuts Node     │◄─┼───────────────► │  │  Nuts Node     │  │
                    │  │  (sidecar)     │  │                 │  │  (sidecar)     │  │
                    │  └────────────────┘  │                 │  └────────────────┘  │
                    └──────────────────────┘                 └──────────────────────┘

  Every cross-org boundary uses Nuts-verified organizational identity.
  Same pluginlake software. Role determined by config + Nuts credentials.
```

### Middleware integration

The Nuts Node runs as a sidecar container alongside the pluginlake services.
A FastAPI middleware validates incoming inter-station requests on every node (both Processing Hub and datastation):

1. Extract the JWT access token from the `Authorization` header.
2. Introspect it via the Nuts Node's `/internal/auth/v1/accesstoken/introspect` endpoint (localhost, no network round-trip).
3. Populate the request context with the authenticated identity (`organization`, `purposeOfUse`).
4. The existing `require_role`/`require_auth` dependencies in `security.py` use this context for route-level authorization.

For requests from data users to the Processing Hub, the user's organizational identity must also be verified (see Data user authentication below).
The Nuts middleware activates for any cross-organizational call, whether between stations or from a data user to the Processing Hub.
For purely local admin requests (CLI on the same machine), a local API key may be used.

### Data user authentication

#### How Nuts handles identity: organizations and users

Nuts operates at the **organization level**. Each DID (`did:nuts`) represents a care organization (a hospital, registry, or research institute), not an individual user.

User identity is a separate layer built into the Nuts OAuth2 flow. When a user wants to act on behalf of an organization, they sign a "contract" — a statement like "I hereby declare to act on behalf of Hospital X." Nuts supports two mechanisms for this:

- **Employee Identity:** the organization's system vouches for the user by providing their identifier, name, and role to the Nuts Node, which creates a Verifiable Presentation (VP).
- **IRMA:** the user proves their identity via the IRMA app using citizen credentials (BRP, email), independently verified.

The signed contract (VP) is included when the Nuts Node requests an OAuth2 access token from the receiving party's Nuts Node. The resulting JWT therefore carries *both* organizational identity *and* user identity. When the receiving party introspects the token, it sees: `username`, `initials`, `family_name`, `assurance_level`, plus the organization's DID.

This is important: **Nuts does not treat user authentication as something separate from the organization flow.** The user contract is embedded in the same OAuth2 token exchange that authenticates the organization.

#### Multi-tenancy: one Nuts Node per organization

The Nuts Node is explicitly **not multi-tenant** ([SaaS Considerations](https://nuts-node.readthedocs.io/en/v5.4/pages/technology/saas.html#multi-tenancy)). Anyone with access to a Nuts Node's API can read and use any credential present on it. The Nuts documentation recommends running a separate Nuts Node for each organization.

This has a direct implication for the Processing Hub. If the Processing Hub only serves users from its own organization (e.g. IKNL Data users using the IKNL Processing Hub), one Nuts Node with one DID is sufficient. But if the Processing Hub serves users from *multiple* organizations (an Amsterdam UMC Data user and a Leiden UMC Data user both querying the same IKNL Processing Hub), the Processing Hub needs a way to handle multi-org user access.

#### What this means for the data user → Processing Hub boundary

The data user → Processing Hub interaction is a cross-organizational boundary. A Data user from Amsterdam UMC querying the IKNL Processing Hub must be identified as an Amsterdam UMC employee, not as a generic "IKNL user."

The Nuts-native way to handle this: the user's organization (Amsterdam UMC) has its own Nuts Node. The Data user signs a `PractitionerLogin` contract at Amsterdam UMC's Nuts Node. That VP is included in an access token request to the Processing Hub's Nuts Node. The Processing Hub introspects the token and gets: the user's identity (name, email) + the user's organization DID (Amsterdam UMC) + that the token was issued for `purposeOfUse: pluginlake-query-access`.

The flow looks like this:

1. Data user opens the Processing Hub's web UI or Python client.
2. The Processing Hub redirects to the Data user's organization's Nuts Node (or the Data user provides their org's DID).
3. The Data user signs a `PractitionerLogin` contract (Employee Identity or IRMA).
4. Amsterdam UMC's Nuts Node obtains an access token from the Processing Hub's Nuts Node, including the signed VP.
5. The Processing Hub validates the token via introspection: gets org DID + user identity.
6. The Processing Hub looks up which `NutsAuthorizationCredential`s exist for Amsterdam UMC's DID → determines which collaborations and catalogs the Data user can access.
7. Only results from those federations are visible to this Data user.

This means every consuming organization needs a Nuts Node, which is realistic since most participating organizations already run one as a datastation. The user never interacts with Nuts directly — the contract signing happens through the UI, similar to an SSO redirect.

#### Alternative: federated OIDC with DID binding

If requiring every consumer organization to have a Nuts Node is too restrictive (e.g. academic Data users at institutions without healthcare infrastructure), an alternative is to accept institutional OIDC tokens (SURFconext, Entra ID) and map the OIDC issuer to a known Nuts DID. This is simpler for the user (standard SSO login) but introduces a mapping that must be maintained and verified. See governance question 6.

#### Result: unified request context

Regardless of the mechanism, after authentication the Processing Hub's request context contains:

- `user_identity`: the user's name, identifier, role (from the VP or OIDC claims).
- `organization_did`: the verified DID of the user's organization (from Nuts token introspection or OIDC-to-DID mapping).
- `accessible_collaborations`: which `NutsAuthorizationCredential`s exist for that organization DID (derived at request time).

This context is used for credential-scoped access control, audit logging (who from which organization queried what), and ensuring a Data user can only see results from collaborations their organization participates in.

### Node roles: Processing Hub and datastation

Every node in the network runs the same pluginlake software.
What a node *does* is determined by two things: its local configuration and the Nuts credentials it holds.

| Aspect | Datastation | Processing Hub |
|---|---|---|
| Local data | Yes (DuckLake, OMOP CDM, FHIR ingestion) | No (data ingestion disabled) |
| Query assets (Dagster) | Yes (executes queries on local data) | No (dispatches queries to datastations) |
| SDC assets (Dagster) | No | Yes (applies statistical disclosure control on combined results) |
| Nuts Node | Yes (own DID) | Yes (own DID) |
| Nuts auth middleware | Yes (validates Processing Hub requests) | Yes (validates datastation responses, incoming admin calls) |
| Receives queries from | Processing Hub (via Nuts JWT) | Data users (via org-verified auth) |
| Issues credentials to | Processing Hub's DID (grants data access) | Nobody (receives credentials from datastations) |

A pluginlake configuration option (e.g. `role: Processing Hub` or `role: datastation`) activates the correct modules.
The gateway enforces this role by checking `purposeOfUse` values:

- A datastation rejects outgoing requests with `purposeOfUse: pluginlake-query-dispatch` (only Processing Hubs dispatch).
- A Processing Hub rejects incoming requests that try to execute local query assets (it has no data).

This means there is no separate Processing Hub codebase.
Adding a Processing Hub to the network is deploying another pluginlake instance with a different config profile and its own Nuts Node.

### What is a collaboration?

A collaboration in the PLUGIN network is a bilateral trust agreement between a datastation (hospital) and a Processing Hub (research coordinator).

In concrete terms, a collaboration is one digital credential: a `NutsAuthorizationCredential` issued by a datastation to a Processing Hub.
This credential is the datastation saying: "I, Hospital X, allow Processing Hub Y to query these specific tables, with these filters, until this date."

That single credential *is* the collaboration.
There is no central registry, no approval board, no shared database of collaborations.
The credential lives on the Nuts network, visible only to the two parties involved.

A **federation** is the collection of all bilateral credentials that point to one Processing Hub.
When IKNL (oncology Processing Hub) has credentials from 15 hospitals, that set of 15 credentials *is* the IKNL oncology federation.
Each hospital independently decided to participate by issuing its own credential.
Each hospital can revoke its credential at any time, instantly leaving the federation.

What this means in practice:

- **Starting a collaboration:** the datastation operator issues a credential to the Processing Hub's DID through the pluginlake UI.
- **Ending a collaboration:** the datastation operator revokes the credential. The Processing Hub can no longer obtain access tokens.
- **Changing scope:** the datastation revokes the old credential and issues a new one with different table, filter, or time period permissions.
- **No central authority:** nobody except the datastation can grant or revoke access to its data.

### Network topology and role identity

The PLUGIN network supports many-to-many relationships between Processing Hubs and datastations.
Multiple Processing Hubs can exist (e.g. IKNL for oncology, DHD for quality indicators, a university for a specific study), and each Processing Hub independently receives bilateral credentials from whichever datastations participate in its collaboration.
A single datastation can issue credentials to multiple Processing Hubs.

```
                 Processing Hub-A (oncology)
                  ┌───┐
         ┌───────►│DID│◄────────┐
         │        └───┘         │
    credential              credential
         │                      │
     ┌───┴───┐              ┌───┴───┐
     │Hosp. 1│              │Hosp. 2│
     └───┬───┘              └───┬───┘
         │                      │
    credential              credential
         │        ┌───┐         │
         └───────►│DID│◄────────┘
                  └───┘
                 Processing Hub-B (quality registry)
```

Technically, Processing Hub and datastation are the same pluginlake software.
What makes a node a "Processing Hub" or a "datastation" is the combination of three things:

1. **Dagster definitions (configuration):** which asset groups and code locations are loaded. pluginlake already composes definitions via `Definitions.merge()` in `pluginlake/definitions/` (see [ADR-001](adr-001-asset-architecture.md)). A datastation loads the existing data ingestion definitions (`pluginlake.definitions.omop`, `pluginlake.definitions.fhir`) plus a new **aggregate definitions** module (`pluginlake.definitions.aggregate`) that registers query assets and the `GET /catalog` endpoint. A Processing Hub loads a new **SDC definitions** module (`pluginlake.definitions.sdc`) that registers SDC assets (small cell suppression, k-anonymity checks, aggregation functions) and the query dispatch + `POST /queries` endpoint. These are two separate Dagster code locations that are never loaded together on the same instance.

   | Definitions module | Loaded on | Assets | API endpoints |
   |---|---|---|---|
   | `pluginlake.definitions.omop` | Datastation | `omop_raw_clinical_tables`, `omop_clinical_tables`, `omop_vocabulary_tables` | Existing ingestion endpoints |
   | `pluginlake.definitions.fhir` | Datastation | `fhir_raw_tables`, `fhir_to_omop_tables` | Existing ingestion endpoints |
   | `pluginlake.definitions.aggregate` (new) | Datastation | Predefined query assets (e.g. `count_per_group`, `cohort_summary`) | `GET /catalog`, `POST /execute` (query asset execution) |
   | `pluginlake.definitions.sdc` (new) | Processing Hub | SDC assets (`small_cell_suppression`, `k_anonymity_check`, aggregation functions) | `POST /queries` (dispatch), `GET /catalog` (merged from datastations) |

2. **Nuts credentials:** which `NutsAuthorizationCredential` VCs the node holds and which `purposeOfUse` values those credentials grant. A datastation issues credentials to a Processing Hub's DID, granting access to specific tables, filters, and time periods. A Processing Hub receives these credentials and uses them to obtain OAuth2 tokens for query dispatch. The credentials define the access boundary — a Processing Hub can only query what the credential explicitly allows.

3. **Data connections:** whether the node has a local DuckLake with patient data (datastation) or operates without local data (Processing Hub). A datastation has `pluginlake.core.ducklake` configured with OMOP schemas and FHIR data. A Processing Hub has no DuckLake or an empty one used only as temporary scratch space for SDC processing (no persistent patient data).

None of these are enforced by Nuts itself. Nuts provides the bilateral trust layer (DIDs, credentials, tokens). The role enforcement happens in pluginlake: the gateway checks the configured role against the `purposeOfUse` in incoming/outgoing requests, and the Dagster definitions determine which assets are available to execute.

### Federation topologies

The Nuts credential model allows several network configurations. Not all are equally safe.

#### One Processing Hub, many datastations (standard federation)

This is the primary model. One Processing Hub (e.g. IKNL oncology) receives `NutsAuthorizationCredential`s from participating hospitals. Each credential is bilateral and scoped. The Processing Hub aggregates results and applies SDC.

```
  Hosp. A ──credential──► Processing Hub (IKNL oncology) ◄──credential── Hosp. B
                                ▲
                                │
                           credential
                                │
                            Hosp. C
```

#### One Processing Hub, multiple federations (multi-scope)

A single Processing Hub DID can receive credentials with different data scopes, effectively hosting multiple logical federations on the same infrastructure. IKNL could run both an oncology federation (credentials scoped to cancer tables from 30 hospitals) and a rare disease federation (credentials scoped to different tables from 12 hospitals).

The Processing Hub distinguishes federations by the credential's data scope. SDC is applied per federation: results from the oncology federation are never mixed with rare disease results.

This works because credentials are bilateral and self-describing. The Processing Hub does not need separate configuration per federation — it derives the structure from the credentials it holds.

#### Multiple Processing Hubs in the network (distinct purpose)

Multiple Processing Hubs can coexist in the PLUGIN network, each serving a different analytical purpose. IKNL runs an oncology Processing Hub, DHD runs a quality indicators Processing Hub, a university runs a study-specific Processing Hub. Hospitals issue credentials to whichever Processing Hubs they participate with.

This is the many-to-many topology already described: each Processing Hub is independent, each hospital decides independently which Processing Hubs to trust.

#### Multiple Processing Hubs for the same data (dangerous)

If two Processing Hubs both receive credentials for the same tables from the same hospitals, both see the raw aggregate results independently. A data user with access to both Processing Hubs could cross-reference suppressed cells between the two outputs and reconstruct data that SDC was designed to hide.

Example: Processing Hub-A suppresses a group of 3 patients. Processing Hub-B, running a slightly different query on the same data, returns a group that includes those 3 patients in a larger bucket. Combining both outputs reveals the hidden group.

Nuts does not prevent this — credentials are bilateral, and a hospital can issue identical scopes to multiple Processing Hubs. This must be a governance rule: a hospital should not issue overlapping data-scope credentials to multiple Processing Hubs unless the SDC implications are explicitly accepted.

#### No Processing Hub (not supported)

A federation without a Processing Hub is not possible in the PLUGIN model. The Processing Hub has three structural responsibilities that cannot be distributed:

1. **Aggregation:** individual datastation results must be combined before they reach the data user.
2. **SDC enforcement:** small cell suppression must be applied to the *combined* result, not to individual hospital results (a group of 2 at Hospital A and 3 at Hospital B is a group of 5 in total — safe to release, but suppressed if each hospital applied SDC independently).
3. **Access gateway:** data users connect to the Processing Hub, never directly to datastations. The Processing Hub handles Nuts token acquisition on their behalf.

Without a Processing Hub, each datastation would need to apply SDC on its own results (losing cross-hospital group size information), or data users would need direct Nuts-authenticated access to each datastation (losing the single access point and audit trail).

A peer-to-peer model without a Processing Hub is architecturally different and not what PLUGIN proposes.

| Topology | Valid | SDC safe | Notes |
|---|---|---|---|
| 1 Processing Hub, many datastations | Yes | Yes | Standard federation |
| 1 Processing Hub, multiple data scopes | Yes | Yes | Separate SDC per scope |
| Multiple Processing Hubs, distinct federations | Yes | Yes | Each Processing Hub independent |
| Multiple Processing Hubs, overlapping data scopes | Technically possible | No | Governance must prevent |
| No Processing Hub | No | N/A | Contradicts PLUGIN model |

### Bolt specification and credential scopes

A Bolt is a protocol specification that defines the rules for inter-station communication.
pluginlake defines one Bolt (`pluginlake-federation`) that describes:

- The allowed `purposeOfUse` values:
  - `pluginlake-query-dispatch` (Processing Hub→datastation): the Processing Hub dispatches a query to a datastation for execution.
  - `pluginlake-data-serve` (datastation→Processing Hub): the datastation returns results to the Processing Hub.
  - `pluginlake-query-access` (consumer org→Processing Hub): a data user's organization accesses the Processing Hub to submit queries and view results.
- The credential types required per purpose.
- The API endpoints each purpose may call.

This means the Bolt defines three cross-organizational boundaries, each with its own credential type:

| Boundary | Credential issuer | Credential subject | purposeOfUse | What it grants |
|---|---|---|---|---|
| Datastation → Processing Hub | Datastation | Processing Hub's DID | `pluginlake-query-dispatch` | Processing Hub may query specific tables, filters, time period |
| Processing Hub → consumer org | Processing Hub | Consumer org's DID | `pluginlake-query-access` | Org's users may submit queries and view results on this Processing Hub |

The Processing Hub issues `pluginlake-query-access` credentials to consumer organizations. This is the reverse direction of data access credentials: datastations grant data access *to* the Processing Hub, and the Processing Hub grants query access *to* consumer organizations. A consumer organization without this credential cannot obtain access tokens for the Processing Hub.

Every station runs the same Bolt. Actual collaborations are `NutsAuthorizationCredential` VCs. Each credential encodes:

- The requesting organization's DID (the Processing Hub).
- A data scope: which tables, column filters, and time period the Processing Hub may query.
- The `purposeOfUse` (must match the Bolt).
- The validity period.

| Layer | What it contains | Scope | Visibility |
|---|---|---|---|
| Bolt specification | Protocol rules, allowed purposes, required credentials | Network-wide | Public (same for all stations) |
| `NutsAuthorizationCredential` | One collaboration: Processing Hub↔datastation, with data scope | Bilateral | Private (only issuer + subject) |

Credentials can also contain computation scopes (which query assets or algorithm types are permitted), enabling future algorithm governance.

### Query execution model

Queries are never raw SQL. Every query is a predefined Dagster asset on the datastation.

1. A data user submits a query via the Processing Hub (UI or Python client). The Processing Hub verifies the user's identity and organizational DID (see Data user authentication). The Processing Hub checks that the user's organization holds a `pluginlake-query-access` credential for this Processing Hub.
2. The Processing Hub validates query parameters against a Pydantic schema.
3. For each relevant datastation, the Processing Hub's Nuts Node obtains an OAuth2 token using the `NutsAuthorizationCredential`.
4. The Processing Hub dispatches the query asset call to each datastation with the Nuts JWT.
5. Each datastation's middleware validates the token, checks the credential scope and `purposeOfUse`, and executes the Dagster asset locally.
6. Results are returned to the Processing Hub. The Processing Hub applies SDC assets (e.g. small cell suppression for groups < k).
7. Only the SDC-processed output reaches the data user. Raw results are not stored on the Processing Hub.

Each datastation publishes a catalog of available query assets (`GET /catalog`), so the Processing Hub and data users know what is available per collaboration.

#### Partial failure handling

When the Processing Hub dispatches a query to multiple datastations, some may fail or time out.
The architectural policy: **SDC correctness is only guaranteed on complete results.** If some datastations fail, the Processing Hub returns a partial result with a manifest (which datastations contributed, which failed). The data user decides whether the partial result is usable. The Processing Hub never silently drops failed datastations.

#### Operational concerns

The following topics are architecturally relevant but are implementation-level concerns addressed in [E6: Operationele hardening en schaalbaarheid](https://github.com/plugin-healthcare/pluginlake/issues/78):

- **Async query dispatch and result polling:** Dagster runs are async. The Processing Hub dispatches, receives a `query_id`, and polls for results. Result TTL and expiry handling are required.
- **Versioning and catalog compatibility:** the catalog includes schema versions per asset. The Processing Hub checks compatibility before dispatching.
- **Nuts Node availability:** hard dependency. No graceful degradation (token caching would accept revoked credentials). Operational monitoring required.
- **Rate limiting and backpressure:** datastations enforce per-Processing Hub DID rate limits at the gateway level (not Dagster-level). `429 Too Many Requests` with backoff.

### Deployment

Each station's Docker Compose adds a Nuts Node sidecar:

```yaml
services:
  nuts-node:
    image: nutsfoundation/nuts-node:v5.4
    environment:
      NUTS_CONFIGFILE: /opt/nuts/nuts.yaml
    ports:
      - "1323:1323" # internal API (localhost only)
      - "5555:5555" # gRPC (public, mTLS)
    volumes:
      - "./config/nuts/nuts.yaml:/opt/nuts/nuts.yaml:ro"
      - "./config/nuts/certificate.pem:/opt/nuts/certificate.pem:ro"
      - "./config/nuts/key.pem:/opt/nuts/key.pem:ro"
      - "./config/nuts/truststore.pem:/opt/nuts/truststore.pem:ro"
      - "nuts-data:/opt/nuts/data"
```

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Centralized OAuth2 (Keycloak, Entra ID) | Contradicts federated model: single identity provider = single point of failure and political barrier. |
| Mutual TLS only | Authenticates the machine, not the user or purpose. Cannot express per-patient, per-purpose authorization. |
| Custom token exchange protocol | Duplicates what Nuts provides, without the Dutch healthcare ecosystem. |
| Direct Nuts Node API exposure | Bypasses the gateway, losing centralized logging, rate limiting, and composability with local auth (ADR-005). |

## Consequences

- Every node runs the same pluginlake software. Role (Processing Hub or datastation) is determined by which Dagster definitions modules are loaded, which Nuts credentials the node holds, and which data connections are configured.
- Two new Dagster definitions modules will be added: `pluginlake.definitions.aggregate` (datastation: query assets, catalog) and `pluginlake.definitions.sdc` (Processing Hub: SDC assets, query dispatch, aggregation functions).
- Each node must run a Nuts Node sidecar (~200 MB memory, negligible Processing Hub at rest) with its own DID.
- Station operators need PKIoverheid certificates for the production network.
- A `pluginlake-federation` Bolt specification defines three `purposeOfUse` values: `pluginlake-query-dispatch` (Processing Hub→datastation), `pluginlake-data-serve` (datastation→Processing Hub), `pluginlake-query-access` (consumer org→Processing Hub).
- Collaboration contracts are `NutsAuthorizationCredential` VCs on the Nuts DAG, encoding data scopes (tables, filters, time period) and distributed privately.
- Consumer organizations receive `pluginlake-query-access` credentials from the Processing Hub to access the federation.
- The gateway enforces the configured role: it rejects `purposeOfUse` values that don't match the node's role.
- Queries are always Dagster assets with Pydantic-validated parameters, never raw SQL.
- The Processing Hub applies SDC assets on combined results. Raw data never leaves the datastation; raw intermediate results are not stored on the Processing Hub.
- Partial query failures are handled transparently: the response includes a manifest of which datastations contributed and which failed.
- Operational concerns (async dispatch, versioning, rate limiting, monitoring) are addressed in [E6: Operationele hardening en schaalbaarheid](https://github.com/plugin-healthcare/pluginlake/issues/78).
- The Nuts Node sidecar is a hard dependency for inter-station auth. No graceful degradation; operational monitoring must ensure availability.
- The FastAPI middleware gains a dependency on the local Nuts Node for token introspection.
- Each station enforces rules locally; no central policy engine. A compromised node cannot forge credentials issued by others.
- All cross-organizational auth (user→Processing Hub and Processing Hub→datastation) is tied to Nuts organizational identity. Local admin access (CLI) may use API keys.
- Data users access the network exclusively through the Processing Hub. The Processing Hub verifies their organizational identity and handles Nuts token acquisition on their behalf.

## Open governance questions

The following questions require stakeholder decisions before production deployment.

### 1. Can a Processing Hub and datastation share the same instance?

It is technically possible to run both roles on the same machine: two separate Nuts Nodes (each with its own DID), two Dagster asset groups (query assets + SDC assets), one shared pluginlake gateway that routes based on which DID the request targets.
The credentials remain cryptographically separate.

However, colocation carries risks:

| Concern | Separate instances | Colocated on same machine |
|---|---|---|
| Container escape / OS-level vulnerability | One role compromised, other isolated | Both roles compromised simultaneously |
| Ops mistakes (wrong env var, shared volume) | Cannot accidentally cross-link | Risk of misconfiguration leaking data between roles |
| Incident response ("which DID was compromised?") | Clear: one host = one role | Ambiguous: must determine which DID was affected |
| Audit trail (NEN 7513) | Clean: each instance has one purpose | Must distinguish two audit streams on one machine |
| SDC integrity | Processing Hub has no local data by definition | Processing Hub process runs alongside local patient data |
| Infrastructure cost | Two deployments per hospital | One deployment, lower cost |

**Engineering recommendation:** for development and testing, colocation is fine.
For production healthcare deployments, separate instances is the safer default.
This decision should be made by the security architect and data protection officer based on the hospital's risk appetite and NEN 7510 ISMS.

### 2. Who approves new collaborations?

A collaboration starts when a datastation issues a `NutsAuthorizationCredential` to a Processing Hub's DID.
Nuts does not require any approval workflow: issuing a credential is a single API call.

The question: who within a hospital is authorized to issue that credential?
Options include the data protection officer, a research committee, or a designated data steward.
pluginlake needs to define whether credential issuance goes through an approval flow in the UI or is a direct administrative action.

### 3. What are the SDC thresholds?

The Processing Hub applies statistical disclosure control (SDC) on combined query results before they reach the data user.
The key parameter is the minimum group size *k* for small cell suppression: groups smaller than *k* are masked.

Who decides the value of *k*? Options:

- A network-wide default (e.g. k=5).
- A per-collaboration setting encoded in the credential.
- Configurable per query by the data user, within bounds set by the credential.

A higher *k* is safer but reduces analytical utility.

### 4. Credential lifetime and renewal

Each `NutsAuthorizationCredential` has a validity period. Questions to resolve:

- What is the default validity period? (e.g. 1 year, duration of a study, indefinite until revoked)
- Is there automatic renewal, or must each credential be manually reissued?
- What happens to in-flight queries when a credential expires?
- Who monitors upcoming expirations?

### 5. Algorithm and query governance

Datastations expose predefined query assets via their catalog. As the network matures:

- Who decides which query assets a datastation offers?
- Can a Processing Hub request custom query assets, or only use what is in the catalog?
- Should the credential contain a computation scope that restricts which asset types are permitted?
- Is there an approval process for adding new query types to the network?

### 6. Data user authentication mechanism

The Processing Hub must verify that a data user belongs to a specific organization in the Nuts network.
Nuts natively supports this through the `PractitionerLogin` / `BehandelaarLogin` contract flow: the user signs a contract at their own organization's Nuts Node, and the resulting access token carries both org DID and user identity.

However, this requires every consuming organization to run a Nuts Node.
For organizations that already participate as datastations this is no extra cost.
For external research institutions without healthcare infrastructure, it may be a barrier.

The alternative is federated OIDC (SURFconext, Entra ID) with a verified mapping from OIDC issuer to Nuts DID.

| Approach | How it works | Pros | Cons |
|---|---|---|---|
| Nuts contract flow (recommended) | User signs `PractitionerLogin` at their org's Nuts Node → access token carries org DID + user identity → Processing Hub introspects | Fully consistent with all other boundaries; no separate identity system; org identity cryptographically proven; user identity in audit trail | Every consuming org needs a Nuts Node; contract signing UX (employee identity or IRMA) must be integrated in the pluginlake UI |
| Federated OIDC + DID mapping | User logs in via institutional SSO → Processing Hub maps OIDC issuer claim to a Nuts DID → org identity derived from mapping | Standard SSO experience; no Nuts awareness needed by the user | Requires maintaining a trusted OIDC-to-DID mapping; mapping correctness is an operational risk; two identity systems to maintain |

**Engineering recommendation:** start with the Nuts contract flow for organizations that already have a Nuts Node (which is all datastations and Processing Hub operators).
Consider OIDC as a future extension for external academic users if the Nuts Node requirement proves to be an adoption barrier.
Both approaches produce the same request context (user + verified org DID), so downstream logic is identical.

## Related documents

- [ADR-001: Asset Architecture](adr-001-asset-architecture.md): Dagster definitions and `Definitions.merge()` pattern
- [ADR-005: FastAPI Gateway](adr-005-fastapi-gateway.md): the gateway that Nuts middleware integrates into

## References

- [Nuts Node documentation (v5.4)](https://nuts-node.readthedocs.io/en/v5.4/)
- [Nuts authentication guide](https://nuts-node.readthedocs.io/en/v5.4/pages/getting-started/5-authentication.html)
- [Nuts authorization guide](https://nuts-node.readthedocs.io/en/v5.4/pages/getting-started/6-adding-authorizations.html)
- [Nuts security model](https://nuts-node.readthedocs.io/en/v5.4/pages/technology/security_model.html)
- [W3C DIDs](https://www.w3.org/TR/did-core/)
- [W3C Verifiable Credentials](https://www.w3.org/TR/vc-data-model/)
