# Federated Infrastructure Comparison

This document evaluates federated infrastructure platforms relevant to pluginlake, a federated data lakehouse for Dutch healthcare.
It covers architecture patterns, authentication, authorization, collaboration workflows, federated computation, and privacy features.
Each platform is assessed for maturity, healthcare readiness, and regulatory alignment.

The goal is to answer a practical question: does pluginlake need an external federated learning framework (such as vantage6) for federated computations, or can it achieve its goals with its current stack?

pluginlake is a federated data lakehouse where each hospital runs its own data station.
Stations exchange data and query each other without a central identity provider.
The data layer is DuckDB/DuckLake, with OMOP CDM for clinical data modeling and FHIR ingestion managed by Dagster.
A FastAPI gateway exposes query and data access endpoints.
Authentication and authorization will be handled by a Nuts Node sidecar (W3C DIDs, Verifiable Credentials, OAuth2 token exchange), as documented in [ADR-006](../decisions/adr-006-nuts-node-decentralized-auth.md).

## 1. Scope and method

We evaluate three categories of infrastructure:

1. Dutch healthcare infrastructure: Nuts Node, KIK-V (as a Nuts reference implementation).
2. EU dataspace infrastructure: HealthData@EU Central Platform (EHDS2), EDC/iSHARE/Gaia-X.
3. Federated learning platforms: Flower, vantage6, NVIDIA FLARE, PySyft, OpenFL, Brane, FedML, and others.

| Criterion | What we assess |
|---|---|
| Architecture topology | Client-server, peer-to-peer, hybrid |
| Authentication and authorization | How nodes prove identity and how access is enforced |
| Collaboration model | How organizations form and manage partnerships |
| Federated computation | What can be computed across nodes |
| Privacy features | Differential privacy, secure aggregation, encryption |
| Healthcare readiness | Compliance, audit trails, patient data handling |
| Maturity | Release stability, production deployments, maintenance |

Sources include official documentation, source code repositories, and the academic literature collected in [docs/papers/](../papers/).

---

## 2. Platform catalog

### 2.1 Nuts Node

[Nuts](https://nuts-node.readthedocs.io/en/v5.4/) is an open-source, decentralized identity and authorization infrastructure for Dutch healthcare.
It provides the trust layer that pluginlake will use for inter-station authentication and authorization.

| Aspect | Details |
|---|---|
| **Topology** | Peer-to-peer with bootstrap nodes. All nodes hold a full replica of the transaction DAG. |
| **AuthN** | W3C DIDs (`did:nuts`) backed by PKIoverheid certificates. Node-to-node: gRPC with mTLS. User sessions: Verifiable Presentations (IRMA/Yivi, UZI). |
| **AuthZ** | `NutsAuthorizationCredential` VCs grant per-patient, per-resource, per-purpose access. OAuth2 JWTs via the `/n2n` endpoint. |
| **Collaboration** | Organizations discover each other via the DID registry. Collaboration is formalized through Bolt specifications (application-specific trust agreements). VCs exchanged privately. |
| **Computation** | None. Nuts is a trust and identity layer. Computation happens in applications that use Nuts for auth. |
| **Privacy** | Data stays at the station unless authorized. Access auditable (NEN 7513). Credentials distributed privately. |
| **Healthcare** | Purpose-built for Dutch healthcare: NEN 7510/7512/7513, AVG/GDPR, Wegiz, Wabvpz. Production deployments across Dutch vendors. |
| **Stack** | Go binary. REST API (OpenAPI 3.0) + gRPC. Docker sidecar (~200 MB). 256 MB RAM, 1 vCPU typical. GPLv3. |

Nuts is the selected auth backbone for pluginlake (see [ADR-006](../decisions/adr-006-nuts-node-decentralized-auth.md)).
It is not a computation platform; it complements federated learning frameworks by providing trust.

#### How the Nuts network works

Nuts is "decentralized" in the sense that no single party controls identity or access decisions, but it still forms a peer-to-peer network.

**Network formation:**

1. A new node connects to one or more bootstrap nodes (just regular peers) over gRPC with mTLS.
2. The bootstrap node shares a copy of the network's transaction DAG (append-only, signed).
3. After initial sync, the new node discovers other peers from the transaction data and connects directly. The bootstrap node is not special after this point.
4. All nodes hold a full replica of the DAG and validate every transaction independently.

There is no central server, registry, or single point of failure. The network is permissioned (all nodes must present a certificate from an agreed-upon CA, e.g. PKIoverheid in production).

**Identity layer (DIDs + Verifiable Credentials):**

- Each organization gets a `did:nuts:...` identifier (public/private key pair).
- The DID becomes meaningful when a trusted party issues a `NutsOrganizationCredential` linking the DID to a real organization name and identifiers.
- DID Documents are propagated through the network automatically.

**Authentication flow:**

1. A practitioner signs a contract ("I act on behalf of Hospital X") using a supported means: employee identity, IRMA/Yivi, or UZI card.
2. This produces a Verifiable Presentation (cryptographic proof of identity + organization affiliation).
3. The requesting station's Nuts node uses this VP to request an OAuth2 access token from the data-holding station's Nuts node (`/n2n` endpoint).
4. The access token is a standard JWT that the data holder's API can validate.

**Authorization flow:**

1. The data holder issues a `NutsAuthorizationCredential` specifying: which patient, which resources, which requesting organization, and for what purpose.
2. This credential is distributed privately over the authenticated node-to-node connection.
3. When an access token is requested, the Nuts node checks the authorization credential before issuing. The API never sees raw credentials, only validated access tokens.

| Concern | Handled by | Where it runs |
|---|---|---|
| DID management, key storage | Nuts Node | Sidecar container per station |
| Credential issuance and verification | Nuts Node | Sidecar container per station |
| User authentication (contract signing) | Nuts Node `/public` API + browser | Nuts Node + user's browser/IRMA app |
| OAuth2 access token issuance | Nuts Node `/n2n` API | Node-to-node, mTLS |
| Access token validation | FastAPI middleware | pluginlake API gateway |
| Resource-level access control | FastAPI middleware | pluginlake API gateway |
| Audit logging | FastAPI middleware + Nuts Node | Both |

#### Bolt specifications and collaboration enforcement

A Bolt is a functional and technical specification that translates a use case into concrete access rules.
It is a protocol definition, not a collaboration registry: it describes what interactions are possible, not who is currently interacting.

pluginlake defines one Bolt (`pluginlake-federation`) that describes:

- The allowed `purposeOfUse` values (e.g. `pluginlake-query-dispatch`, `pluginlake-data-serve`).
- The credential types required per purpose.
- The API endpoints each purpose may call.
- The data scopes available per purpose.

Every station runs the same Bolt specification. Actual collaborations are represented as individual `NutsAuthorizationCredential` VCs issued by the data-holding station to the requesting station. Each credential encodes:

- The requesting organization's DID.
- The data scope (tables, cohort filter, date range).
- The purpose of use (must match a value defined in the Bolt).
- The validity period.

| Layer | What it contains | Scope | Visibility |
|---|---|---|---|
| Bolt specification | Protocol rules, allowed purposes, required credentials | Network-wide | Public (same for all stations) |
| `NutsAuthorizationCredential` | One collaboration between specific parties | Bilateral | Private (only issuer + subject) |

#### Decentralized contract storage

Collaboration credentials are stored on the Nuts network's transaction DAG:

- The DAG is an append-only, cryptographically signed, distributed ledger replicated across all Nuts Nodes.
- When a station issues a `NutsAuthorizationCredential`, it is written as a signed transaction.
- The credential is distributed privately using Nuts' `pal` (Participants Access List) header, encrypted with the public keys of only the intended recipients.
- Each station's Nuts Node maintains a local copy of only the credentials it is allowed to see.
- Revocation also happens on the DAG: the issuer publishes a revocation transaction.

Every station that is party to a collaboration has an independent, locally verifiable copy of the contract. No station depends on a central server to discover or validate its agreements.

#### Security model: compromised nodes

1. **Credentials cannot be forged.** Each VC is signed by the issuing station's DID private key. A compromised requesting node cannot fabricate a credential.
2. **The DAG is append-only.** A compromised node cannot rewrite or delete existing transactions. Authorization credentials are issued by the data holder (not the requester).
3. **Credentials can be revoked.** Issuing stations can revoke all VCs granted to a compromised station's DID. Existing tokens expire within their short TTL.
4. **The private key is the blast radius.** If a station's own key is compromised, the attacker can impersonate that station. Other stations' keys are unaffected. The response is to rotate the DID's key material.
5. **Short-lived access tokens limit exposure.** Nuts OAuth2 tokens have a configurable TTL (typically minutes).

### 2.2 KIK-V

[KIK-V](https://kik-v.nl/) is a Dutch program for nursing care data exchange, built on the Nuts network.
The [technical specifications (v1.1.3)](https://kik-v-publicatieplatform.nl/documentatie/nuts-technischespecificaties/1.1.3) describe the full protocol.

| Aspect | Details |
|---|---|
| **Topology** | Decentralized via Nuts. Each care organization runs its own Nuts node. |
| **AuthN/AuthZ** | Inherits Nuts DIDs + VCs. PKIoverheid certificates. mTLS transport. |
| **Data model** | OWL2/RDF ontologies. SPARQL 1.1 queries. SHACL parameter validation. |
| **Messaging** | Asynchronous DIDComm over Nuts. Point-to-point, no intermediary. |
| **Governance** | Structured matching process: data consumers and providers agree on queries through the KIK-V management organization. Validated queries are issued as `ValidatedQueryCredential` VCs. |
| **Maturity** | Operational. [Afsprakenset v3.1.0](https://kik-v-publicatieplatform.nl/afsprakenset/3.1.0). Multiple exchange profiles published for IGJ, NZa, VWS. |

KIK-V validates the Nuts approach for healthcare data exchange. Key patterns for pluginlake:

| KIK-V pattern | pluginlake equivalent |
|---|---|
| Validated query as a VC | `PluginlakeQueryCredential` VCs per collaboration |
| SPARQL embedded in credential | SQL query templates or query scopes in credentials |
| SHACL parameter shapes | JSON Schema / Pydantic parameter constraints |
| DIDComm messaging | FastAPI endpoints secured by Nuts OAuth2 |
| Exchange profiles | Bolt specifications for federation agreements |
| Governance-approved queries only | Graduated computation validation levels (see section 3.4) |

### 2.3 HealthData@EU Central Platform (EHDS2)

The [HealthData@EU Central Platform](https://acceptance.data.health.europa.eu/) implements the European Health Data Space for secondary use.
[Release 3](https://op.europa.eu/en/publication-detail/-/publication/52fe4b0e-0ac4-11f0-b1a3-01aa75ed71a1) was [open-sourced](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/blog/2025/03/27/887383631/EHDS2+Central+Platform+3+goes+open+source+with+enhanced+eDelivery+integration) in March 2025 under EUPL 1.2.

| Aspect | Details |
|---|---|
| **Topology** | Four-corner model via eDelivery AS4 (Domibus). National access points mediate between requesters/providers. |
| **AuthN/AuthZ** | API keys internally. eDelivery certificates cross-border. Data permits from national HDABs. |
| **Computation** | Secure Processing Environments mandated by EHDS Art. 50, not yet implemented (expected Release 5-6). |
| **Stack** | Java 17+ (Spring Boot), MongoDB, Apache Camel, Domibus. EUPL 1.2. |
| **Maturity** | Release 3 of 6. Full operational readiness (including SPEs) targeted for Release 6 (~2028-2029). |

HealthData@EU operates at a different layer: EU cross-border routing and permits.
pluginlake operates at the operational level within Dutch healthcare.
The two are complementary; pluginlake could expose datasets through a national access point adapter.

### 2.4 European dataspace protocols (EDC, iSHARE, Gaia-X)

| Protocol | Model | Healthcare fit | Why not chosen |
|---|---|---|---|
| **EDC / Tractus-X** | Control Plane + Data Plane, `did:web`, ODRL policies. Java/Kotlin, 5+ services per participant. Apache 2.0. | Low. No patient-level authz, no UZI/IRMA, no PKIoverheid. Automotive focus. | High integration effort, no healthcare features. |
| **iSHARE** | Dutch trust framework (logistics origin). OAuth2 M2M, central Participant Registry. | Low. No patient-level authz, no DID/VC model. Semi-centralized registry dependency. | Central registry conflicts with decentralized architecture. |
| **Gaia-X** | Governance overlay (specs, compliance labels). Not deployable software. | Neutral. Does not prescribe or prevent healthcare features. | Not an implementation. Complementary as a compliance label. |

Nuts is preferred over all three for pluginlake: purpose-built for Dutch healthcare, patient-level authorization, single sidecar deployment, active Dutch healthcare adoption.
All three share W3C DID/VC primitives and can interoperate with Nuts in the future.

### 2.5 Flower

[Flower](https://flower.ai/) (v1.x/2.x) is an open-source, framework-agnostic federated learning platform.

| Aspect | Details |
|---|---|
| **Topology** | Client-server. SuperLink coordinates SuperNodes. |
| **AuthN/AuthZ** | EC key-based node auth. No RBAC. |
| **Collaboration** | None. Assumes a single operator. Cross-org trust must be built externally. |
| **Computation** | FedAvg, FedSGD, custom strategies. PyTorch, TensorFlow, JAX, scikit-learn. Simulation mode. |
| **Privacy** | Differential privacy (Opacus/TF Privacy). Secure aggregation (SecAgg/SecAgg+). |
| **Healthcare** | No healthcare features. No audit trail. Needs wrapping for healthcare use. |
| **Stack** | Python. gRPC. Docker or pip. Apache 2.0. Flower Cloud (commercial managed). |

pluginml already uses Flower for ML aggregation and training.
Flower does not include built-in trust establishment, access control, or audit logging, so it requires a complementary infrastructure layer for healthcare deployments.

### 2.6 vantage6

[vantage6](https://docs.vantage6.ai/) (v4.x) is a federated analysis infrastructure by [IKNL](https://iknl.nl/), designed for healthcare.

pluginlake currently uses vantage6 in production via the `pluginml` module, and at the current federation size it remains the recommended orchestrator for federated ML workloads.

| Aspect | Details |
|---|---|
| **Topology** | Client-server. Central server coordinates nodes (Docker containers). |
| **AuthN** | Username/password + 2FA. API keys. TLS. |
| **AuthZ** | RBAC (root, admin, researcher, node). Algorithm whitelisting. Per-org permissions. |
| **Collaboration** | First-class concept. Organizations registered on server. Tasks scoped to collaborations. |
| **Computation** | Algorithm containers (any Docker image). Aggregation on server. Subtask chaining. MPC support. |
| **Privacy** | E2E RSA encryption. Algorithm whitelisting. Data stays at node. SSH tunneling for MPC. |
| **Healthcare** | Designed for healthcare. GDPR-aligned. Used in Dutch oncology (IKNL network). Active in Health-RI. |
| **Stack** | Python (Flask). PostgreSQL/SQLite. Docker. RabbitMQ. SocketIO. Apache 2.0. |

Operational experience in the PLUGIN project surfaced architectural trade-offs documented in the [production readiness assessment](../papers/production-readiness-assessment.md).
At scale beyond ~20 nodes, the following trade-offs become relevant:

- Hub-and-spoke: all traffic through a single SocketIO connection per collaboration, saturating before hardware is utilized.
- No control/data plane separation: status polling and large payloads share the same JSON + base64 channel.
- Shared encryption keys per organization with no forward secrecy.
- Central server sees all task metadata across collaborations.
- No per-request auth for node-to-node communication (VPN tunnels instead of transactional auth).

These are trade-offs inherent to vantage6's hub-and-spoke design, which prioritizes simplicity and ease of deployment for small-to-medium federations. For larger federations or use cases requiring per-request cryptographic auth, a complementary trust layer (such as Nuts) fills the gap.

### 2.7 NVIDIA FLARE

[NVIDIA FLARE](https://nvflare.readthedocs.io/) (v2.x) is NVIDIA's enterprise FL framework.

| Aspect | Details |
|---|---|
| **Topology** | Client-server. FL server + FL clients (sites). |
| **AuthN/AuthZ** | PKI with project CA, mTLS. Per-site authorization policies. Admin roles. |
| **Computation** | FedAvg, FedProx, FedOpt, SCAFFOLD. PyTorch, TensorFlow, XGBoost. Controller/Executor API. |
| **Privacy** | DP filters, HE (TenSEAL), TEEs (NVIDIA Confidential Computing). Per-site privacy filters. |
| **Healthcare** | Medical imaging (Clara ecosystem). No NEN/GDPR tooling. GPU-oriented. |
| **Stack** | Python. gRPC. NVIDIA NGC images. Apache 2.0. NVIDIA AI Enterprise (commercial support). |

Strong security and privacy primitives, but assumes GPU infrastructure.
Over-engineered for pluginlake's tabular/SQL workloads.

### 2.8 Other platforms

| Platform | Status | Why not selected |
|---|---|---|
| **PySyft** (OpenMined) | v0.9.x, declining maintenance | Manual code review model is appealing but API breaks across versions. OpenMined pivoted. High risk. |
| **OpenFL** (Intel) | Stable, niche | Medical imaging focus (FeTS). No RBAC. Limited value for SQL/aggregate workloads. |
| **Brane** (UvA) | Archived Oct 2025 | Excellent policy reasoner concept. Rust/K8s. Dead codebase, design patterns worth studying. |
| **FedML / TensorOpera** | OSS abandoned Oct 2023 | Pivoted to proprietary SaaS. Incompatible with data sovereignty. |
| **Substra** (Owkin) | Active, v0.47+ | Strong privacy model. Requires Kubernetes per org. Worth revisiting if pluginlake moves to K8s. |
| **FATE** (WeBank) | Maintenance mode | Rich MPC/HE. Declining activity. Chinese ecosystem, limited EU healthcare presence. |
| **TensorFlow Federated** | Active | TF-only. Simulation-only, no production deployment infra. |
| **PaddleFL** / **IBM FL** | Low activity / proprietary | Tight ecosystem coupling. No EU healthcare presence. |

---

## 3. Comparison by functional concern

### 3.1 Network topology and collaboration

#### Topology

| Platform | Topology | Central component | Fails if central goes down |
|---|---|---|---|
| Nuts Node | Peer-to-peer | None (bootstrap nodes not privileged) | No |
| KIK-V | Peer-to-peer (via Nuts) | None | No |
| HealthData@EU | Four-corner (eDelivery) | EU routing infrastructure | Yes |
| Flower | Client-server | SuperLink | Yes |
| vantage6 | Client-server | Central server | Yes |
| NVIDIA FLARE | Client-server | FL server | Yes |
| PySyft | Datasite (per-owner) | None (each Datasite centralized) | Per-Datasite |
| OpenFL | Client-server | Aggregator | Yes |
| Brane | Hybrid | Orchestrator | Yes |

#### Collaboration models

| Platform | How collaborations are formed | Collaboration granularity |
|---|---|---|
| Nuts / KIK-V | Bolt specifications + VC-based trust agreements. Governed matching process (KIK-V). Organizations discover each other via DID registry. | Per-query, per-purpose. Credentials scoped and revocable. |
| HealthData@EU | Formal permit application to national HDAB. Routing configured by the platform. | Per-dataset, per-use-case. Permit-scoped. |
| EDC / Tractus-X | Contract negotiation (DSP). ODRL usage policies. Bilateral agreements. | Per-contract, per-asset. |
| Flower | No collaboration model. Single operator assumed. | N/A |
| vantage6 | Organizations registered on central server. Explicit collaboration groups. Tasks scoped to collaborations. | Per-collaboration, per-algorithm. |
| NVIDIA FLARE | Project-based. Admin provisions CA and distributes startup kits. Per-site policies. | Per-project. |
| PySyft | Data scientists discover Datasites. Trust via code review. | Per-computation (manual). |
| OpenFL | Plan-based (YAML). All collaborators agree on plan before training. | Per-experiment. |

#### Communication patterns

| Platform | Transport | Serialization | Direct node-to-node |
|---|---|---|---|
| Nuts | gRPC (mTLS) + REST (HTTPS) | JSON-LD, JWS | Yes (peer-to-peer) |
| KIK-V | DIDComm over HTTPS/mTLS | JSON-LD/Turtle, SPARQL JSON, JWS | Yes (via Nuts) |
| HealthData@EU | AS4/HTTPS (Domibus) | XML (OASIS AS4) | Via access points |
| Flower | gRPC | Protocol Buffers | No (via SuperLink) |
| vantage6 | SocketIO + REST | JSON + base64 | SSH tunnel only (MPC) |
| NVIDIA FLARE | gRPC | Protocol Buffers | No (via FL server) |

### 3.2 Governance and trust

| Platform | Trust model | Who controls access | Policy language | Revocation |
|---|---|---|---|---|
| Nuts | DIDs + VCs, PKIoverheid CA | Each station enforces its own policies | Bolt specifications | Credential revocation via Nuts network |
| KIK-V | Nuts credentials + governance body | KIK-V management org issues query credentials | Matching process + SHACL shapes | Credential revocation (10s leash) |
| HealthData@EU | eDelivery certs, national HDABs | National HDABs issue permits | EHDS Art. 33-37 | Permit expiry/revocation |
| Flower | EC keys | Key holder (single operator) | None | Key rotation |
| vantage6 | Username/2FA, API keys | Central server admin | Server RBAC config | Account/key revocation on server |
| NVIDIA FLARE | PKI with project CA | Project admin + per-site policies | JSON policy files | Certificate revocation |
| PySyft | User accounts, code review | Data owner (manual) | Human judgment | Account removal |

KIK-V's governance model is instructive for pluginlake: queries are predefined (not ad-hoc), parameters are constrained via schemas, providers can reject even valid credentials, and credentials are revocable. This "governance-by-credential" pattern applies directly to pluginlake, with SQL/containers instead of SPARQL.

### 3.3 Authentication and authorization

| Platform | Node/site authN | User authN | AuthZ model | AuthZ granularity | NEN 7512 compliance |
|---|---|---|---|---|---|
| Nuts | mTLS (PKIoverheid) | VPs (IRMA/Yivi, UZI) | Verifiable Credentials | Per-patient, per-resource, per-purpose | Yes (designed for) |
| HealthData@EU | eDelivery certs | API keys (internal) | Data permits (HDABs) | Per-dataset, per-use-case | Via eDelivery |
| EDC | `did:web` + mTLS | Connector admin | ODRL policies | Per-contract, per-asset | No |
| iSHARE | PKI certificates | OAuth2 M2M | Delegation evidence | Per-delegation chain | Partial |
| Flower | EC keys | None | None (key = access) | Binary | No |
| vantage6 | API keys / TLS | Username + 2FA | RBAC + whitelisting | Per-collaboration, per-algorithm | No (API keys insufficient) |
| NVIDIA FLARE | mTLS (project CA) | Admin CLI with roles | Per-site policies | Per-operation, per-site | Partial (PKI, not PKIoverheid) |
| PySyft | None | Email/password | Manual code approval | Per-computation | No |
| OpenFL | mTLS (shared CA) | None | None (cert = access) | Binary | Partial |

Only Nuts natively meets NEN 7512 requirements for trusted electronic communication in healthcare.
Any FL platform used in Dutch healthcare would need Nuts (or equivalent) as the auth layer.

### 3.4 Compute orchestration

#### Task dispatch

| Platform | How tasks are dispatched | Who sees task metadata | Scalability model |
|---|---|---|---|
| KIK-V | Direct DIDComm messages between stations | Only participating parties | Linear (P2P) |
| vantage6 | Central server dispatches to nodes via SocketIO | Central server + participants | Scale the server (bottleneck) |
| Flower | SuperLink dispatches to SuperNodes via gRPC | SuperLink + participants | Scale the SuperLink |
| NVIDIA FLARE | FL server dispatches via gRPC | FL server + sites | Scale the FL server |

#### Algorithm and container management

All FL platforms use containers (Docker images) for algorithm execution.
The key difference is how trust in those containers is established.

| Mechanism | What it proves | Strictness | Tooling |
|---|---|---|---|
| Image digest pinning (SHA256) | Exact binary approved | Highest | Docker/OCI native |
| Container signing (cosign/sigstore) | Trusted party vouches for image | High | [cosign](https://docs.sigstore.dev/cosign/signing/overview/), [Notary v2](https://notaryproject.dev/) |
| SBOM attestation (CycloneDX/SPDX) | Exact dependencies known | Medium-high | [syft](https://github.com/anchore/syft), [grype](https://github.com/anchore/grype) |
| Reproducible builds | Same source = same digest | Highest (when feasible) | [apko](https://github.com/chainguard-dev/apko), deterministic Dockerfiles |
| Source provenance (SLSA) | Built from this commit by this CI | Medium-high | [SLSA](https://slsa.dev/), GitHub Actions attestations |
| Algorithm registry with review | Governance body approved this version | Variable | vantage6 algorithm store, custom |

Graduated validation levels for pluginlake:

| Level | Name | Validated | Use case |
|---|---|---|---|
| 0 | Sandbox | Nothing; synthetic data only | Prototyping, hackathons |
| 1 | Registry-only | Image from approved registry | Exploration with known collaborators |
| 2 | Signed | cosign signature + SBOM scanned | Standard research collaborations |
| 3 | Pinned + attested | Digest pinned in credential, SLSA provenance | Production analytics, regulatory reporting |
| 4 | KIK-V equivalent | Exact computation in VC, parameters schema-constrained, every execution logged | National quality indicators |

vantage6 implements levels 1-2 via tag-based whitelisting, which is appropriate for trusted collaborations. Digest pinning and signing (level 3) can be layered on top for higher-assurance deployments.

#### Aggregation patterns

| Pattern | Platforms | Privacy | Complexity |
|---|---|---|---|
| Central aggregation | vantage6, Flower, FLARE, OpenFL | Aggregator sees all updates | Low |
| Secure aggregation (SecAgg) | Flower (SecAgg+), FLARE (partial) | Individual updates hidden | Medium |
| Homomorphic encryption | FLARE (TenSEAL) | Computation on encrypted data | High |
| TEE-based | FLARE (NVIDIA CC) | Hardware-level isolation | High (requires NVIDIA hardware) |
| No aggregation (query results only) | KIK-V, pluginlake planned | Each station returns independent result | Lowest |

### 3.5 Privacy and security

| Platform | DP | SecAgg | Encryption | HE/MPC | TEE | Data stays at source |
|---|---|---|---|---|---|---|
| Nuts | N/A | N/A | TLS + encrypted VCs | No | No | Yes (by design) |
| HealthData@EU | No | No | TLS + eDelivery signing | No | SPEs (future) | Yes (permit-scoped) |
| Flower | Yes (Opacus) | Yes (SecAgg+) | TLS | No | No | Yes |
| vantage6 | No | No | E2E RSA | Partial (SSH for MPC) | No | Yes |
| NVIDIA FLARE | Yes (filters) | Yes | TLS | Yes (TenSEAL) | Yes (NVIDIA CC) | Yes |
| PySyft | Partial | No | TLS | Partial (CrypTen) | No | Yes (code review) |
| OpenFL | Yes (basic) | Planned | TLS | No | No | Yes |

### 3.6 Regulatory compliance

| Requirement | Nuts | vantage6 | Flower | NVIDIA FLARE | HealthData@EU |
|---|---|---|---|---|---|
| GDPR data minimization | ✅ data at source | ✅ results only | ⚠️ manual | ⚠️ manual | ✅ permit-scoped |
| GDPR lawful basis tracking | ✅ VCs encode purpose | ⚠️ collaboration metadata | ❌ | ❌ | ✅ permits |
| EHDS Art. 50 (SPEs) | N/A | ⚠️ Docker (partial) | ❌ | ⚠️ TEE | ⚠️ planned |
| NEN 7510 (ISMS) | ✅ designed for | ⚠️ no guidance | ❌ | ❌ | ⚠️ EU-level |
| NEN 7512 (trusted comm.) | ✅ PKIoverheid + mTLS | ⚠️ TLS + API keys | ❌ | ✅ PKI + mTLS | ⚠️ eDelivery |
| NEN 7513 (access logging) | ✅ built in | ⚠️ task logging | ❌ | ⚠️ admin logging | ⚠️ planned |
| Wegiz (electronic exchange) | ✅ designed for | N/A | N/A | N/A | N/A |
| Wabvpz (patient rights) | ⚠️ access logging | ❌ | ❌ | ❌ | ⚠️ planned |

Key gaps:

1. **No FL platform addresses NEN 7510/7512/7513 natively.** Only Nuts is designed around these Dutch standards. Any FL platform needs Nuts (or equivalent) underneath.
2. **EHDS Secure Processing Environments are not yet available.** NVIDIA FLARE's TEE is closest but requires NVIDIA hardware.
3. **Lawful basis tracking is absent from all FL platforms.** Only Nuts (VCs with `purposeOfUse`) and HealthData@EU (permits) address this.
4. **Audit trails are incomplete.** NEN 7513 requires patient-level logging. FL platforms log tasks, not patient-record access. This must be filled by pluginlake regardless of FL choice.
5. **Patient rights (Wabvpz) are not addressed by any FL platform.** This is a data platform responsibility that constrains how FL can be deployed.

---

## 4. PLUGIN platform

### 4.1 Module overview

PLUGIN is a modular platform of independent packages:

| Module | Purpose | Status |
|---|---|---|
| pluginlake | Data lakehouse: DuckDB/DuckLake, OMOP CDM, FHIR ingestion, Dagster, FastAPI gateway | Implemented |
| pluginml | Federated ML: Flower-based aggregation, FederatedTransformer, training pipelines | Implemented (v0.3, on Flower + vantage6) |
| pluginhub | Data exchange: secure federated data sharing between stations | Planned |
| pluginanalytics | Federated queries: distributed SQL analytics across stations | Planned |

Each module is a separate package with its own dependencies.
pluginml is built on Flower (`flwr==1.22.0`) and vantage6 (`vantage6==4.13.0`), and can connect to a pluginlake instance as a data source.
Together, these modules provide capabilities that FL platforms lack: structured healthcare data management, data cataloging, SQL-based federated queries, healthcare identity (via Nuts), data quality and provenance (via Dagster), and NEN 7513-compliant audit logging.

### 4.2 Architecture options

| Aspect | vantage6 only | Hybrid (vantage6 + Nuts) | Native decentralized (Nuts only) |
|---|---|---|---|
| Topology | Hub-and-spoke | Hub-and-spoke for compute, P2P for auth | Peer-to-peer |
| Metadata visibility | Central server sees all | Server sees task metadata, auth in Nuts | Only participating stations |
| Points of failure | Server + nodes | Server + nodes (auth survives outage) | Nodes only |
| Auth strength | API keys + 2FA | PKIoverheid mTLS + VCs | PKIoverheid mTLS + VCs |
| Algorithm validation | Tag-based whitelisting | Tags (v6) + digest/signature (Nuts VCs) | Digest-pinned, signed, attested |
| Infra per station | v6 node + pluginlake | v6 node + pluginlake + Nuts Node | pluginlake + Nuts Node |
| Central infra | v6 server + PostgreSQL + RabbitMQ | v6 server + PostgreSQL + RabbitMQ | Container registry only |
| Time to production | Fastest | Medium | Slowest |
| Long-term governance | Central operator required | Central operator for compute | Governance body for algorithm approval only |

### 4.3 Hybrid scenario

The hybrid keeps vantage6 for orchestration while complementing it with Nuts for organizational identity and per-request auth:

**What it solves:** API-key auth upgraded to PKIoverheid mTLS + VCs (meeting NEN 7512), per-request node-to-node auth via Nuts OAuth2, per-request authorization via VCs (replacing shared encryption keys), and structured audit trail (Nuts + pluginlake logging).

**What it does not solve:** the coordination model properties (hub-and-spoke topology, single connection per node, shared control/data plane) remain. These are acceptable for medium-scale federations and are separate from the auth concerns that Nuts addresses.

**When it makes sense:** medium-scale federations (~5-20 organizations); leveraging the vantage6 ecosystem (IKNL algorithms, Health-RI collaborations); team bandwidth favors proven infrastructure over building new.

### 4.4 Native decentralized option

In a fully decentralized model, orchestration flows station-to-station via Nuts, following the KIK-V pattern generalized to container execution:

```
Requesting Station                     Data Station
┌──────────────┐                      ┌──────────────┐
│ pluginlake   │  1. Discover (Nuts)  │ pluginlake   │
│ FastAPI      ├─────────────────────►│ FastAPI      │
│              │  2. OAuth2 token     │              │
│              │  3. POST /compute    │              │
│              │     (image digest,   │  4. Verify   │
│              │      params, VP)     │  5. Pull     │
│              │                      │  6. Execute  │
│              │◄─────────────────────┤  7. Sign     │
│ 8. Aggregate │  signed result (JWS) │              │
└──────────────┘                      └──────────────┘
```

No central server involved. The requesting station aggregates results from all participating stations locally.

For federated queries (pluginanalytics), there is no iterative aggregation: each station returns a result, the requester combines them.
For iterative model training (pluginml), the requesting station acts as the Flower aggregator.
Privacy concerns (aggregator sees intermediate weights) can be addressed by Flower's SecAgg without requiring Flower's SuperLink infrastructure.

### 4.5 Open questions

1. **Multi-round aggregation privacy.** When the requesting station aggregates model weights, it sees all individual contributions. SecAgg hides these, but correct implementation is nontrivial. How much privacy risk is acceptable initially?

2. **Container runtime isolation.** Running containers against patient data requires strong isolation. Options: network-isolated execution, read-only volumes, resource limits, gVisor/Kata. What level per validation level?

3. **Large result transfer.** Intermediate model weights can be tens of megabytes. Is Nuts mTLS performant enough, or is a dedicated data channel needed?

4. **Algorithm compatibility.** pluginml algorithms use vantage6's `@data()` and `@algorithm_client` decorators. A compatibility shim would be needed, or algorithms must be re-packaged.

5. **pluginml migration path.** Replacing `PluginVantage6Client`, `run_v6`/`execute_v6_step`, and decorator patterns while keeping Flower integration (PLUGINClient, PLUGINStrategy) unchanged. Are there hidden coupling points?

---

## 5. Recommendation

| Use case | Recommendation | Rationale |
|---|---|---|
| Federated aggregate queries | Build (pluginanalytics + Nuts) | FastAPI + DuckDB handles this. No FL framework needed. Queries bypass vantage6. |
| Federated SQL analytics | Build (pluginanalytics) | DuckDB SQL + Nuts discovery/auth. No orchestrator needed. |
| Secure data exchange | Build (pluginhub + Nuts) | Nuts provides discovery and auth. Avoids central server dependency. |
| Container-based computation | Build (`/compute` endpoint + Nuts) | No new infrastructure. Container validation levels provide governance. |
| Federated ML (short term) | Hybrid (Nuts auth on existing vantage6) | Keep pluginml on vantage6. Add Nuts for NEN 7512. Lowest disruption. |
| Federated ML (long term) | Evaluate: reassess when federation exceeds vantage6's operational comfort zone (>20 nodes, high concurrency) | pluginml keeps Flower for ML. If scale demands outgrow vantage6's coordination model, the `/compute` endpoint provides a migration path. |
| Federated deep learning (GPU) | Evaluate NVIDIA FLARE if GPU workloads become frequent | Requesting-station-as-aggregator works for rare GPU tasks. FLARE for frequent ones. |
| vantage6 ecosystem interop | Build adapter (if needed) | Thin compatibility shim for existing `@algorithm_client`/`@data()` algorithms. |
| Cross-border EHDS | Integrate with HealthData@EU when available (Release 5-6) | National access point adapter. |

---

## 6. User-facing access patterns

Not every participant in the pluginlake network holds data.
Hospitals run full data stations (FastAPI + DuckLake + Dagster + Nuts Node).
Researchers or analytics teams may only need to query across stations.

Every organization that participates needs its own DID and its own Nuts Node instance.
The Nuts Node is [not multi-tenant](https://nuts-node.readthedocs.io/en/v5.4/pages/technology/saas.html): anyone with API access to a node can read all credentials on that node.
A single shared node cannot safely serve multiple independent organizations.

| Option | Description | Trade-off |
|---|---|---|
| Query station (self-hosted) | Minimal pluginlake deployment: FastAPI gateway + Nuts Node, no data pipeline. | Full identity sovereignty; requires local infra. |
| Query station (cloud-hosted) | Multi-tenant query platform where each requesting organization gets its own Nuts Node container and gateway. | Low barrier to entry; hosting party manages infra but each org keeps its own DID. |
| Piggyback on a data station | Researcher authenticates at a hospital's station and queries through it. Identity tied to the hospital's DID. | Simplest; but audit trail shows the hospital, not the researcher's organization. |

Individual users never interact with Nuts directly.
They authenticate against their organization's gateway using local auth (API key, OIDC, username/password), and the gateway handles Nuts-level federation on their behalf.

**Onboarding friction.** The Nuts onboarding burden (DID registration, PKIoverheid certificate, Nuts Node deployment) is per-organization, not per-user, but non-trivial.
The cloud-hosted option reduces this to an administrative step.
Individual researchers never touch Docker, DIDs, or certificates.

---

## 7. EU dataspace detailed comparison

This section provides detailed analysis of EU dataspace initiatives compared to Nuts Node for pluginlake.

### Eclipse EDC / Tractus-X

EDC is the reference implementation of DSP and DCP, wrapped by Tractus-X for automotive.
It separates a Control Plane (catalog, negotiation, transfer protocol) from a Data Plane (HTTP, S3, blob transfer), uses `did:web` for identity, and enforces usage policies via ODRL.

EDC offers full EU dataspace standard alignment, formal contract negotiation, and broad multi-sector adoption.
However, it is written in Java/Kotlin with no Python SDK, requires 5+ services per participant, and has no healthcare-specific features: no patient-level authorization, no UZI/IRMA integration, no PKIoverheid CA hierarchy.

### iSHARE

iSHARE is a Dutch trust framework (logistics origin) using PKI-based identity, OAuth2 M2M auth, and a centralized Participant Registry.
Its delegation model is production-proven in Dutch data spaces and Gaia-X aligned.

For pluginlake, the main drawbacks are the semi-centralized Participant Registry dependency, the lack of healthcare-specific features, and certificate-based identity rather than DIDs/VCs.

### Gaia-X

Gaia-X is a governance overlay (trust framework, compliance labels), not deployable software.
A pluginlake deployment could be Gaia-X-compliant while using Nuts Node for the actual identity/auth runtime.

### EHDS and HealthData@EU

EHDS is regulation, not technology (entered into force March 2025, application from 2029).
The HealthData@EU Central Platform implements the cross-border routing layer using a four-corner model via eDelivery AS4 (Domibus).

| Aspect | HealthData@EU Central Platform | pluginlake + Nuts Node |
|---|---|---|
| **Purpose** | EU-level secondary use catalogue and cross-border routing | Federated data lakehouse for multi-site clinical analytics |
| **Scope** | National HDABs to Central Platform (regulatory level) | Hospital stations to research query stations (operational level) |
| **Communication** | eDelivery AS4 (store-and-forward) | Direct HTTPS + gRPC (Nuts mTLS, synchronous) |
| **Identity** | Delegated to member state; API keys between components | Decentralized DIDs + VCs (Nuts) per organization |
| **AuthZ** | Data permits from Health Data Access Bodies | `NutsAuthorizationCredential` per collaboration (cryptographic) |
| **Data flow** | Metadata catalogue sync; data via secure processing environments | Query at source; only aggregated results cross boundaries |

These layers are complementary. If cross-border integration becomes required, a National Dispatcher adapter could translate between AS4 messages and pluginlake's REST API.

### Why Nuts remains the recommended choice

| Criterion | Nuts Node | EDC/Tractus-X | iSHARE |
|---|---|---|---|
| Healthcare fit | Purpose-built for Dutch healthcare | Generic (automotive focus) | Generic (logistics origin) |
| Patient-level authz | `NutsAuthorizationCredential` per patient/resource | Not supported natively | Not supported natively |
| Identity integration | IRMA/Yivi, UZI, PKIoverheid | `did:web` only | PKI certificates only |
| Operational complexity | Single sidecar container (~200 MB) | 5+ services per participant | Participant Registry dependency |
| Python ecosystem | REST API (httpx), sidecar pattern | Java/Kotlin only | REST API, limited libraries |
| Decentralization | Fully P2P after bootstrap | P2P but needs DID web hosting | Semi-centralized |
| Dutch healthcare adoption | Active deployments + Nuts Foundation | None | Limited healthcare adoption |
| EU standards alignment | W3C DIDs + VCs (same primitives as DCP) | Full DSP + DCP | OAuth2 + PKI (DCP on roadmap) |

### Future-proofing strategy

- **Phase 1 (now):** Adopt Nuts Node for inter-station auth in the Dutch healthcare context.
- **Phase 2 (~2027):** Evaluate whether Nuts evolves toward DCP or whether a lightweight DSP adapter is needed.
- **Phase 3 (~2029):** If cross-border exchange is required, add a DSP control plane that delegates identity to Nuts Node.

---

## 8. Regulatory compliance for clinical data exchange

pluginlake exchanges clinical (health) data between federated stations.
This section maps each regulation to its key requirements and assesses compliance posture.

### EU regulations

#### GDPR (Regulation (EU) 2016/679)

Health data are "special category" data under Article 9.

| Requirement | Status | Notes |
|---|---|---|
| Lawful basis (Art. 6 + Art. 9) | Planned | Each station's controller must establish lawful basis per use case. |
| DPIA (Art. 35) | Not started | Required before deploying processing of health data at scale. |
| Data minimisation (Art. 5(1)(c)) | Partial | API endpoints can scope responses; not yet enforced systematically. |
| Right of access/portability (Art. 15, 20) | Partial | FastAPI exposes data per patient, but no self-service portal yet. |
| Breach notification (Art. 33-34) | Not implemented | 72-hour notification to AP required. |
| Records of processing (Art. 30) | Not implemented | Must document all processing activities per station. |

#### EHDS (Regulation (EU) 2025/327)

Entered into force March 2025. Application phased: 2027 (digital health authorities), 2029 (primary+secondary use rights), 2031 (extended primary use).

| Requirement | Status | Notes |
|---|---|---|
| European EHR exchange format (Art. 15) | Partial | pluginlake uses FHIR; implementing acts for exact format due March 2027. |
| Patient access to health data (Art. 3) | Not started | Required from 2029. |
| EHR system conformity (Art. 39, Annex II) | Not started | Manufacturers must demonstrate conformity (CE marking). |
| Secondary use via HDABs (Ch. IV) | Not applicable yet | Pseudonymisation and secure processing environment required. |
| Logging of access (Annex II, 3.2) | Planned | Nuts Node + FastAPI middleware log access events. |
| Right to opt out (Art. 71) | Not started | Must implement when secondary use is supported. |

#### NIS2 (Directive (EU) 2022/2555)

Covers healthcare as a critical sector.

| Requirement | Status | Notes |
|---|---|---|
| Risk management (Art. 21) | Partial | Nuts mTLS, encrypted storage, access controls. Formal risk assessment not documented. |
| Incident reporting (Art. 23) | Not implemented | 24h early warning, 72h full notification to CSIRT. |
| Supply chain security (Art. 21(2)(d)) | Partial | Dependencies via `uv`/`pyproject.toml`. No formal SBOM. |
| Business continuity (Art. 21(2)(c)) | Not implemented | Backup, disaster recovery, crisis management needed. |

#### CRA (Regulation (EU) 2024/2847)

Applies from December 2027. Medical devices excluded from CRA but EHDS requires EHR systems to demonstrate CRA conformity.

| Requirement | Status | Notes |
|---|---|---|
| Software Bill of Materials (Annex I, Part II) | Not implemented | Generate from `pyproject.toml`/`uv.lock`. |
| Vulnerability handling (Annex I, Part II) | Not implemented | Coordinated vulnerability disclosure needed. |
| Security by design (Annex I, Part I) | Partial | Nuts mTLS, JWT validation, role-based access. Need threat model. |

#### eIDAS (Regulation (EU) No 910/2014, amended by eIDAS2 (EU) 2024/1183)

| Requirement | Status | Notes |
|---|---|---|
| Accept eIDAS-recognised eID for patient access | Not started | Required when patient-facing services are built. |
| Health professional auth via recognised eID | Planned | Nuts supports IRMA/Yivi and UZI (Dutch eID aligned). |
| PKIoverheid certificates for machine identity | Planned | Required for Nuts Node production deployment. |

### Dutch regulations and standards

#### Wegiz (Stb. 2023, 99)

| Requirement | Status | Notes |
|---|---|---|
| Electronic exchange of designated data | Partial | pluginlake supports FHIR-based exchange. AMvB alignment TBD. |
| Use of designated standards | Partial | Depends on AMvB-prescribed standards per exchange type. |

#### Wabvpz (Stb. 2017, 446)

| Requirement | Status | Notes |
|---|---|---|
| Patient electronic access to records | Not started | No patient-facing portal yet. |
| Logging of all access to patient records | Planned | Nuts Node + FastAPI middleware. NEN 7513 format TBD. |
| Patient consent for electronic exchange | Planned | `NutsAuthorizationCredential` can encode patient-level consent. UX needed. |

#### NEN 7510 (Information security management in healthcare)

| Requirement | Status | Notes |
|---|---|---|
| ISMS | Not started | Documented policies, risk assessment, continuous improvement. Organizational per station. |
| Access control | Partial | Nuts identity + FastAPI RBAC. Formal policy not documented. |
| Cryptographic controls | Partial | mTLS (TLS 1.3), JWT signing, DuckDB encryption at rest. Key management TBD. |

#### NEN 7512 (Trusted electronic communication)

| Requirement | Status | Notes |
|---|---|---|
| Authentication of communicating parties | Compliant | Nuts mTLS with PKIoverheid certificates. |
| Communication security | Compliant | gRPC with mTLS; HTTPS with JWT tokens. |
| Trust establishment | Compliant | DID-based trust with VCs and network consensus. |

#### NEN 7513 (Logging of access to health records)

| Requirement | Status | Notes |
|---|---|---|
| Log: user identity, role, organization | Planned | Nuts token provides `sub`, `iss`, `purposeOfUse`. |
| Log: patient identity | Planned | Link each access event to the patient(s) whose data were accessed. |
| Log: timestamp, action type | Planned | FastAPI middleware captures this. Format per NEN 7513 TBD. |
| Log retention (min. 5 years per Wabvpz) | Not implemented | Need durable, tamper-evident storage per station. |

### Compliance summary

| Regulation | Layer | Current | With Nuts | Key gaps |
|---|---|---|---|---|
| GDPR | EU | Partial | Improved | DPIA, breach procedures, records of processing |
| EHDS | EU | Low | Improved | Patient access, exchange format, EHR certification |
| NIS2 | EU | Low | Improved | Risk assessment, incident reporting, business continuity |
| CRA | EU | N/A yet | Improved | SBOM, vulnerability handling |
| eIDAS | EU | Not started | Improved | Cross-border eID, wallet integration |
| Wegiz | NL | Partial | Improved | AMvB-designated standard alignment |
| Wabvpz | NL | Low | Improved | Patient portal, consent UX, log retention |
| NEN 7510 | NL | Low | Improved | ISMS, documented policies |
| NEN 7512 | NL | Good | Compliant | Minimal gaps |
| NEN 7513 | NL | Low | Improved | Formatted audit log, retention policy |

### Key compliance actions (priority order)

1. **Complete a DPIA** (GDPR Art. 35) before production deployment with real patient data.
2. **Document an ISMS** (NEN 7510) or align with the station operator's existing ISMS.
3. **Implement structured audit logging** per NEN 7513, with 5-year retention (Wabvpz).
4. **Establish incident response procedures** for GDPR (72h) and NIS2 (24h early warning).
5. **Generate SBOMs** from `uv.lock` for CRA readiness.
6. **Verify Wegiz alignment** per AMvB-designated data exchanges.
7. **Plan a patient access service** for Wabvpz and EHDS (Art. 3-4) by 2029.
8. **Monitor EHDS implementing acts** (due March 2027) for exchange format and certification requirements.

---

## 10. Operational design for federated query dispatch

This section documents the operational design for executing federated queries across multiple datastations, covering async dispatch, result management, failure handling, versioning, rate limiting, and monitoring.
These concerns are referenced by [ADR-006](../decisions/adr-006-nuts-node-decentralized-auth.md) (architecture) and Epic E6 in the [Epics & Stories](../decisions/epics-analytics.md) (implementation).

### 10.1 Async dispatch via Dagster

Dagster jobs on datastations are asynchronous. The CPU does not maintain a long-running HTTP connection.
The dispatch pattern is:

1. The CPU calls `POST /execute` on the datastation with the query asset name, parameters, and Nuts JWT.
2. The datastation validates the token and parameters, starts a Dagster run, and returns `202 Accepted` with a `query_id`.
3. The CPU polls `GET /execute/{query_id}/status` periodically. Possible statuses: `pending`, `running`, `completed`, `failed`, `expired`.
4. On `completed`, the CPU retrieves the result via `GET /execute/{query_id}/result`.
5. The CPU repeats 3-4 for each datastation in the query.

Polling is preferred over push notifications because:

- The CPU controls retry logic and timing.
- No reverse auth direction needed (the datastation would need a Nuts token to call back the CPU).
- If the CPU is temporarily unreachable, no push is lost: results wait on the datastation.
- Polling is battle-tested in federated systems (Flower, EHDS proposals, S3 multipart).

The CPU manages polling state internally. This maps naturally to a Dagster sensor on the CPU side that checks pending queries across datastations.

### 10.2 Result storage and TTL

Query results are stored on the datastation with a configurable TTL (e.g. 24 hours). After the TTL expires, the result is deleted and the status changes to `expired`.

**Result expiry is a real risk.** If the CPU dispatches to 10 datastations and takes 2 hours to retrieve the last result (because the first 9 took long), station 10's result may have expired. The CPU must handle `expired` status by re-dispatching that specific station.

Design requirements:

- The TTL must be long enough to accommodate the slowest query in the federation plus polling overhead.
- The CPU should track per-station result age and prioritize retrieval of results approaching TTL.
- Results are never persisted beyond their TTL. This supports the "no raw data stored on CPU" policy: the datastation controls how long intermediate results exist.

### 10.3 Token renewal during long queries

Nuts JWTs have a short TTL (configurable, typically minutes). For long-running async queries, the CPU must re-obtain tokens for each polling call.

This is cheap: token acquisition from the local Nuts Node is a localhost call with no network round-trip. The credential is still valid (its lifetime is much longer than the token's). The overhead is negligible.

However: if the underlying `NutsAuthorizationCredential` is revoked while a query is in progress, the CPU can no longer obtain new tokens. The in-flight query continues on the datastation (it was already started), but the CPU cannot retrieve the result. This is correct behavior: revocation means "access revoked now," not "access revoked retroactively."

### 10.4 Partial failure and manifest

When the CPU dispatches to multiple datastations, some may fail or time out. The SDC correctness guarantee depends on complete results (a group of 2 at Hospital A and 3 at Hospital B is a group of 5 in total: safe to release, but suppressed if each hospital applied SDC independently).

**Architectural policy: SDC correctness is only guaranteed on complete results.**

The CPU returns a manifest with every query response:

```json
{
  "manifest": {
    "total_datastations": 10,
    "completed": ["did:nuts:hosp-a", "did:nuts:hosp-b", ...],
    "failed": [
      {"did": "did:nuts:hosp-c", "reason": "timeout", "retryable": true},
      {"did": "did:nuts:hosp-d", "reason": "version_incompatible", "retryable": false}
    ]
  },
  "is_complete": false,
  "sdc_applied": true,
  "result": { ... }
}
```

The CPU never silently drops failed datastations. The data user decides whether a partial result is usable.

### 10.5 Versioning and catalog compatibility

Hospitals upgrade pluginlake at different paces. The catalog is the compatibility checkpoint.

The `GET /catalog` response includes per query asset:

- `name`: the asset identifier (e.g. `count_per_group`).
- `description`: human-readable description.
- `parameter_schema`: JSON Schema of accepted parameters.
- `schema_version`: semantic version of the parameter schema (e.g. `1.2.0`).
- `pluginlake_version`: the pluginlake version that introduced this asset version.

Before dispatching, the CPU compares the `schema_version` in the datastation's catalog against the version it expects:

- **Same major version:** compatible. The CPU dispatches normally.
- **Different major version:** breaking change. The CPU skips the datastation and records a `version_incompatible` error in the manifest.
- **Minor version difference:** the CPU adapts if possible (e.g. uses only parameters that the older schema supports) or skips.

The version check happens *from the cached catalog*, not as a separate pre-dispatch call. The catalog is refreshed periodically (e.g. every hour) and on-demand when dispatching.

### 10.6 Rate limiting at the gateway

Dagster's internal run concurrency limits manage resource allocation on a single instance. They do not protect against external load.

The problem: if 5 CPUs each fire 10 queries, that's 50 incoming HTTP requests. Every request is accepted, authenticated (Nuts introspection), and handed to Dagster before concurrency limits kick in. The gateway connections, Nuts Node CPU for introspection, and Dagster scheduling overhead are all consumed.

The datastation must protect itself at the gateway level:

- **Per-CPU DID rate limit in FastAPI middleware:** max concurrent query executions (e.g. 5) and max queries per minute (e.g. 30).
- **`429 Too Many Requests`** with `Retry-After` header: instant signal to the CPU to back off.
- **CPU implements exponential backoff** when receiving `429`.
- Rate limits are configurable per CPU DID (a high-priority CPU can get higher limits).

Dagster's concurrency limits are a safety net (defense in depth), not the rate limiting mechanism.

### 10.7 Health checks and monitoring

Each node exposes health status for operational monitoring:

- **Nuts Node:** health endpoint on port 1323. Hard dependency: if down, the station is unreachable. Restart on failure.
- **Datastation health:** composite endpoint reporting Nuts Node status, Dagster daemon status, DuckLake connectivity.
- **CPU health:** reports Nuts Node status plus reachability of all configured datastations (last successful catalog fetch, last successful query).

For initial deployment, health checks are HTTP endpoints consumed by Docker health checks or a monitoring system. Prometheus metrics export (query latency, failure rate, rate limit hits per CPU DID) is a future optimization.

---

## 9. References

### Papers

- Lo, S.K., et al. (2022). Architectural patterns for the design of federated learning systems. *J. Systems & Software*, 191, 111357. [doi:10.1016/j.jss.2022.111357](https://doi.org/10.1016/j.jss.2022.111357)
- "A federated infrastructure for European data spaces." *Commun. ACM*, 65 (2022): 44-45. [doi:10.1145/3512341](https://doi.org/10.1145/3512341)
- Mammen, P.M. (2021). Federated Learning: Opportunities and Challenges. [arXiv:2101.05428](https://arxiv.org/abs/2101.05428)
- Li, Q., et al. (2021). A survey on federated learning. *Knowledge-Based Systems*, 216, 106775. [doi:10.1016/j.knosys.2021.106775](https://doi.org/10.1016/j.knosys.2021.106775)
- "Federated learning: Overview, strategies, applications, tools and future directions." *Heliyon* (2024). [doi:10.1016/j.heliyon.2024.e38168](https://doi.org/10.1016/j.heliyon.2024.e38168)

### Platform documentation

- [Nuts Node documentation (v5.4)](https://nuts-node.readthedocs.io/en/v5.4/)
- [KIK-V publication platform](https://kik-v-publicatieplatform.nl/)
- [KIK-V program](https://kik-v.nl/)
- [HealthData@EU Central Platform](https://acceptance.data.health.europa.eu/)
- [EHDS2 Release 3 Architecture](https://op.europa.eu/en/publication-detail/-/publication/52fe4b0e-0ac4-11f0-b1a3-01aa75ed71a1)
- [HDEU source code](https://code.europa.eu/healthdataeu/healthdataeu-eu-dataset-catalogue)
- [Flower documentation](https://flower.ai/docs/)
- [vantage6 documentation](https://docs.vantage6.ai/)
- [NVIDIA FLARE documentation](https://nvflare.readthedocs.io/)
- [PySyft repository](https://github.com/OpenMined/PySyft)
- [OpenFL documentation](https://openfl.readthedocs.io/)
- [Brane repository (archived)](https://github.com/epi-project/brane)
- [Substra documentation](https://docs.substra.org/)
- [TensorFlow Federated](https://www.tensorflow.org/federated)

### Project documentation

- Vinkesteijn, Y. (2025). *Vantage6 Production Readiness Assessment.* PLUGIN / DHD. [docs/papers/production-readiness-assessment.md](../papers/production-readiness-assessment.md)

### Regulations

- [GDPR — Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
- [EHDS — Regulation (EU) 2025/327](https://eur-lex.europa.eu/eli/reg/2025/327/oj)
- [NIS2 — Directive (EU) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)
- [CRA — Regulation (EU) 2024/2847](https://eur-lex.europa.eu/eli/reg/2024/2847/oj)
- [eIDAS — Regulation (EU) No 910/2014](https://eur-lex.europa.eu/eli/reg/2014/910/oj)
- [eIDAS2 — Regulation (EU) 2024/1183](https://eur-lex.europa.eu/eli/reg/2024/1183/oj)
- [NEN 7510-1:2024](https://www.nen.nl/nen-7510-1-2024-nl-312618)
- [NEN 7512:2022](https://www.nen.nl/nen-7512-2022-nl-297498)
- [NEN 7513:2023](https://www.nen.nl/nen-7513-2023-nl-308704)
- [Wegiz](https://wetten.overheid.nl/BWBR0047840/)
- [Wabvpz](https://wetten.overheid.nl/BWBR0023864/)

### Dataspace technology

- [W3C Decentralized Identifiers (DIDs)](https://www.w3.org/TR/did-core/)
- [W3C Verifiable Credentials](https://www.w3.org/TR/vc-data-model/)
- [Eclipse DCP v1.0.1](https://eclipse-dataspace-dcp.github.io/decentralized-claims-protocol/v1.0.1/)
- [Eclipse DSP](https://github.com/eclipse-dataspace-protocol-base/DataspaceProtocol)
- [Eclipse Tractus-X Connector KIT](https://eclipse-tractusx.github.io/docs-kits/kits/connector-kit/adoption-view)
- [iSHARE Trust Framework](https://framework.ishare.eu/)
- [Gaia-X Architecture](https://gaia-x.eu/what-is-gaia-x/)
- [HEALTH-X dataLOFT](https://www.health-x.org/home)
- [HDEU Dispatcher](https://code.europa.eu/healthdataeu/healthdataeu-eu-dataset-catalogue/hdeu-dispatcher)
- [eDelivery Building Block](https://ec.europa.eu/digital-building-blocks/sites/display/DIGITAL/eDelivery)
