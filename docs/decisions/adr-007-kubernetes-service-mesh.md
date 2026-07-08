# ADR-007: Kubernetes and service mesh as a production deployment profile

- **Status:** Proposed
- **Date:** 2026-06-30
- **Authors:** Yannick Vinkesteijn

## Context

pluginlake is Docker focused today.
Deployment is driven by Docker Compose (`deploy/compose/`), TLS routing by Traefik, and inter-station authentication by a Nuts Node sidecar (see [ADR-006](adr-006-nuts-node-decentralized-auth.md)).
A single station already runs many cooperating containers: the FastAPI gateway (see [ADR-005](adr-005-fastapi-gateway.md)), three Dagster processes (webserver, daemon, code-server), Postgres, the DuckLake catalog, the Nuts Node sidecar, and one or more UI containers.

In the federated model every node runs the same software but plays one of two roles: `datastation` (holds local patient data, executes query assets) or `Processing Hub` (no persistent patient data, dispatches queries and applies SDC).
These roles have different security profiles. A datastation handles patient data and must be tightly isolated. A Processing Hub aggregates results from multiple organizations and must never colocate with raw data (see [ADR-006](adr-006-nuts-node-decentralized-auth.md), open governance question 1).

Both Dagster and Kubernetes offer richer pod management, security, and network primitives than Docker Compose provides.
Compose has no concept of network policy, pod security admission, per-run isolation, RBAC, or mutual TLS between services.
For healthcare deployments (NEN 7513 auditability, strict network segmentation, least privilege) these gaps matter.

This ADR records what Kubernetes plus a service mesh such as Istio would add, how a Datastation and a Processing Hub would look internally on Kubernetes, how machines would communicate, how this affects authentication, authorization, and the API strategy, and how it affects the currently planned features and modules.
It is exploratory. The decision is to support Kubernetes as an opt-in profile, not to drop Compose.

## Decision

**Adopt Kubernetes as a supported production deployment profile, with an optional service mesh (Istio) for stations that require zero-trust internal networking. Keep Docker Compose as the default for development and small single-node stations.**

Concretely:

- Docker Compose remains the path for local development and for small stations that run on a single host.
- Kubernetes becomes a second, opt-in production profile (`deploy/k8s/`) for stations and Processing Hubs that need stronger isolation, per-run scaling, and policy-based networking.
- A service mesh (Istio, with Linkerd as a lighter alternative) is layered on top of Kubernetes for intra-cluster mutual TLS and per-service authorization. It is optional and orthogonal to the Nuts layer.
- The Nuts Node remains the cross-organizational identity and authorization layer. The mesh does not replace it. The two operate at different boundaries.

This is a deployment and packaging decision. It does not change the application code's responsibilities defined in ADR-001, ADR-005, and ADR-006.

## What Kubernetes adds on security

Kubernetes provides controls that Docker Compose cannot express:

| Capability | Compose today | Kubernetes |
|---|---|---|
| Pod hardening | Per-container `user:` only | Pod Security Admission (restricted): non-root, drop all capabilities, read-only root filesystem, seccomp `RuntimeDefault` |
| Network segmentation | Single bridge network, all containers can reach each other | `NetworkPolicy`: default-deny, explicit allow per service pair |
| Role isolation | Separate compose files | Namespaces per role with their own policies and quotas |
| Secrets | `env_file` bind mount (no encryption) | `Secret` objects, optionally backed by an external vault via the Secrets Store CSI driver |
| Access control | None | RBAC for operators and service accounts |
| Resource limits | `mem_limit` only | Requests, limits, quotas, `LimitRange` per namespace |
| Self-healing | `restart:` policy | Liveness, readiness, and startup probes with controlled rollout |
| Per-run isolation | Dagster runs in shared process | `dagster-k8s` run launcher: each run is its own pod with its own limits, cleaned up on completion |

Two of these are decisive for pluginlake.

**NetworkPolicy.** A datastation namespace can default-deny all traffic and then allow only what the architecture needs: UI to gateway, gateway to Dagster, Dagster to Postgres and DuckLake, gateway to the local Nuts Node, Nuts Node out to the public gRPC port. Nothing else can talk to the Postgres holding patient data. Compose cannot express this.

**Per-run pod isolation for Dagster.** With the `dagster-k8s` run launcher and the `k8s_job_executor`, each query asset run executes in a dedicated pod with its own CPU and memory limits, its own service account, and automatic cleanup. This isolates a heavy or untrusted query from the gateway and from other runs, and gives per-run resource governance that the Compose all-in-one container cannot.

## What a service mesh (Istio) adds

A service mesh injects an Envoy sidecar next to each pod and manages traffic between them.

- **Automatic mutual TLS** between every pod in the cluster, without changing application code. Intra-cluster traffic becomes encrypted and mutually authenticated by default (zero trust inside the cluster).
- **Service-to-service authorization** via `AuthorizationPolicy`: for example, only the gateway service account may call the Dagster service; only the SDC pods may read the scratch DuckLake. This is defense in depth behind the gateway's own authN and authZ.
- **Traffic management**: retries, timeouts, and circuit breaking. This is directly useful for the Processing Hub's query dispatch (partial failure handling) and for the per-DID rate limiting and backpressure noted in ADR-006 (E6 operational hardening).
- **Egress control**: an egress gateway restricts outbound traffic to known destinations only (peer Nuts Nodes, object storage), which limits exfiltration paths from a datastation.
- **Telemetry**: per-service traffic metrics and distributed tracing out of the box, feeding the planned Prometheus and Grafana observability (see [Future Features](../development/future-features.md)).

### Mesh mTLS versus Nuts: two different boundaries

These layers must not be confused:

| Layer | Scope | Identity | Protects |
|---|---|---|---|
| Service mesh mTLS (Istio) | Inside one cluster, service to service | Kubernetes service account / SPIFFE identity | Intra-station traffic between pods |
| Nuts Node (ADR-006) | Across organizations, station to station | Organizational DID, OAuth2 JWT | Cross-org query dispatch and data serving |

The mesh secures traffic between the gateway, Dagster, Postgres, and the Nuts Node inside a station.
The Nuts layer secures traffic between a Processing Hub and a datastation that belong to different organizations.
A request from a data user travels through both: Nuts proves the organization and user across the boundary, the mesh proves the pod identity inside the cluster.

One concrete interaction must be handled: the Nuts Node's public gRPC port (cross-org mTLS, terminated by Nuts itself) must be excluded from the mesh's mTLS or set to `PERMISSIVE`, so Istio does not wrap an already mutually authenticated channel. The Nuts internal API stays localhost only and inside the mesh.

## Internal view: Datastation and Processing Hub on Kubernetes

Each role maps to a namespace (or, for hard isolation, a separate cluster). The pods mirror today's containers.

```
 Datastation namespace                          Processing Hub namespace
 (holds patient data)                           (no persistent patient data)
┌─────────────────────────────────┐           ┌─────────────────────────────────┐
│  ingress-gateway (Istio)         │           │  ingress-gateway (Istio)         │
│        │                         │           │        │                         │
│   ┌────▼─────┐   ┌────────────┐  │           │   ┌────▼─────┐   ┌────────────┐  │
│   │ FastAPI  │   │    UI      │  │           │   │ FastAPI  │   │    UI      │  │
│   │ gateway  │   │ datastation│  │           │   │ gateway  │   │  hub       │  │
│   └────┬─────┘   └────────────┘  │           │   └────┬─────┘   └────────────┘  │
│        │ (mTLS, NetworkPolicy)   │           │        │ (mTLS, NetworkPolicy)   │
│   ┌────▼───────────────────┐     │           │   ┌────▼───────────────────┐     │
│   │ Dagster: webserver,    │     │           │   │ Dagster: webserver,    │     │
│   │ daemon, code-server    │     │           │   │ daemon, code-server    │     │
│   │ runs = isolated pods   │     │           │   │ SDC assets, dispatch   │     │
│   └────┬───────────┬───────┘     │           │   └────────────┬──────────┘     │
│        │           │             │           │                │ scratch only   │
│   ┌────▼────┐  ┌───▼────────┐    │           │   ┌────────────▼──────────┐     │
│   │Postgres │  │ DuckLake   │    │           │   │ DuckLake (ephemeral)  │     │
│   │+catalog │  │ patient PVC│    │           │   │ no patient data       │     │
│   └─────────┘  └────────────┘    │           │   └───────────────────────┘     │
│   ┌──────────────┐               │           │   ┌──────────────┐               │
│   │ Nuts Node    │◄──── gRPC ────┼──── mTLS ──┼──►│ Nuts Node    │               │
│   │ (own DID)    │  cross-org    │           │   │ (own DID)    │               │
│   └──────────────┘               │           │   └──────────────┘               │
└─────────────────────────────────┘           └─────────────────────────────────┘
```

- **Datastation namespace.** A `PersistentVolumeClaim` holds the DuckLake patient data. A default-deny `NetworkPolicy` allows egress only to its own Nuts Node and denies all other outbound traffic. Query asset runs execute as short-lived pods. Pod Security Admission runs everything non-root with a read-only root filesystem.
- **Processing Hub namespace.** No patient `PersistentVolumeClaim`. Any DuckLake present is ephemeral scratch space for SDC, deleted after use. SDC pods are the only workloads that touch combined results. Egress is allowed only to known datastation endpoints through the Nuts Node.
- **Colocation question.** Namespaces with separate `NetworkPolicy`, service accounts, and Pod Security profiles give far stronger isolation than two Compose files on one host. This partially addresses ADR-006 open question 1. For organizations that need hard isolation (container escape resilience, clean NEN 7513 audit streams), separate clusters remain the recommendation.

## Network and communication between machines

- **Intra-station (inside a cluster).** Istio mTLS encrypts and authenticates every pod-to-pod call. `NetworkPolicy` enforces which pods may connect at all. `AuthorizationPolicy` enforces which service identity may call which endpoint. The gateway remains the only path to Dagster and the data, as in ADR-005.
- **Inter-station (across organizations).** Unchanged in principle. A Processing Hub's Nuts Node obtains an OAuth2 token and calls the datastation's Nuts gRPC endpoint. Cross-org mTLS is terminated by Nuts, not the mesh. The Istio ingress gateway replaces Traefik as the TLS entry point and forwards to the gateway and to the Nuts public port.
- **Data user to Processing Hub.** The user reaches the Processing Hub's ingress gateway, the gateway verifies the user's organizational identity via Nuts, and the request proceeds inside the mesh. No change to the trust model, only to where TLS is terminated and how internal hops are secured.

The net effect: the cross-organization protocol (Nuts) is untouched, and a new intra-cluster security layer (mesh plus policy) is added underneath it.

## Effect on authentication, authorization, and the API strategy

Kubernetes and a mesh add a new identity layer underneath the existing model. They do not change who is allowed to see patient data, but they change where transport security and machine identity live, and they reopen the question of which API style to use internally.

### Three authentication and authorization layers

After this change the model has three distinct layers, each answering a different question:

| Layer | Boundary | Identity | Answers | Owner |
|---|---|---|---|---|
| Edge (gateway) | Client to station | API key (local admin) or Nuts org plus user identity | "Is this caller who they claim to be, and may they use this endpoint?" | FastAPI gateway (ADR-005) |
| Cross-organization | Station to station | Organizational DID, Verifiable Credential, OAuth2 JWT | "May this organization query these tables, with these filters, for this purpose?" | Nuts Node (ADR-006) |
| Intra-cluster (new) | Pod to pod | Kubernetes service account / SPIFFE identity | "May the gateway pod call the Dagster pod?" | Service mesh (`AuthorizationPolicy`) |

The important rule: the new mesh layer is **workload identity, not user or data identity**. Mesh `AuthorizationPolicy` decides which service may call which service. It has no concept of a user, an organization, a table, or a Nuts credential scope. It therefore cannot replace the gateway's per-query and per-write authorization, nor the Nuts credential scope that defines which patient data a Processing Hub may touch. It is defense in depth: even if the gateway is bypassed, a pod with no service-account permission still cannot reach Postgres.

Inside a single organization's cluster the mesh identity can simplify internal machine-to-machine trust (for example, internal admin calls between pods can rely on mesh mTLS instead of shared API keys). Cross-organization calls gain nothing from the mesh, because the mesh does not span organizations, and they continue to rely entirely on Nuts.

### Is REST still the obvious choice?

Yes for the external and cross-organization API, with room for gRPC internally.

- **External API (data user to Processing Hub) stays REST.** ADR-005's reasons hold and the mesh does not change them: the OpenAPI contract, broad client and SDK support, human debuggability, and the fact that the Nuts and OAuth2 flows are HTTP based. Healthcare integrators expect REST and FHIR-style interfaces. A mesh secures transport, it does not improve REST ergonomics for external consumers.
- **Cross-organization dispatch (Processing Hub to datastation) stays REST over Nuts.** This boundary crosses organizations, so the mesh does not span it. The transport is an OAuth2-authenticated HTTPS call between two Nuts Nodes. gRPC would add no benefit here and would complicate the Bolt and credential model.
- **Intra-cluster service-to-service is where gRPC becomes more attractive.** The mesh gives gRPC first-class load balancing, retries, and mTLS, and Dagster already uses gRPC for its code locations. For high-volume or streaming internal hops (for example streaming large result sets from the code-server to the gateway) gRPC inside the cluster is a reasonable optimization. This is optional and internal. It must not fragment the single external contract.

Conclusion: keep one REST plus OpenAPI external contract (ADR-005 unchanged). Treat gRPC as an internal, in-mesh optimization to adopt only where it pays off. Do not expose gRPC across the organization boundary.

### Verifiable Credentials in a more closed network

A natural question is whether a more closed network (a hardened cluster, a private mesh, private peering between organizations) reduces the need for Verifiable Credentials. It does not, because the cluster closes the wrong boundary.

- **The mesh closes the intra-organizational network, not the inter-organizational one.** A Datastation and a Processing Hub from different organizations still sit in different trust domains. The mesh's trust root (the cluster CA) stops at the cluster edge. The cross-org gap that Nuts exists to bridge is untouched by making each cluster more closed.
- **Verifiable Credentials carry authorization, not just authentication.** A closed network can give you transport security and machine identity. It cannot give you a bilateral, scoped, revocable, auditable grant. A `NutsAuthorizationCredential` encodes which tables, which filters, which time period, and which `purposeOfUse` a specific Processing Hub may use, and the issuing hospital can revoke it instantly. No network-level control expresses this. This is the core value and it survives any amount of network hardening.
- **Extending one mesh across organizations would recreate a central trust root.** A multi-cluster Istio mesh spanning hospitals and Processing Hubs is technically possible, but it requires a shared trust anchor, which is exactly the centralized model ADR-006 rejects (single point of failure, political barrier, loss of sovereignty). So the mesh deliberately stops at the organization boundary, and Nuts remains the cross-org layer.
- **A genuinely single-tenant closed deployment is the one case that changes.** If one organization runs both a datastation and a Processing Hub inside one cluster for internal-only analysis, the cross-org boundary collapses. There the mesh identity could carry the internal hop and Nuts is not strictly required for that hop. This is the colocation case in ADR-006 open question 1. The moment a second organization joins, the cross-org boundary returns and Verifiable Credentials are required again.

What the closed network does buy is a smaller transport and discovery surface. With private peering an operator may not need public PKIoverheid certificates for every hop, and discovery can be restricted to known peers. That simplifies operations. It does not remove the credential model, because authorization scope, purpose binding, revocability, and bilateral sovereignty are properties of the credential, not of the network.

## Effect on currently planned features and modules

| Area | Source | Effect |
|---|---|---|
| Asset architecture | [ADR-001](adr-001-asset-architecture.md) | No code change. Each Dagster code location becomes a Deployment. The `aggregate` (datastation) and `sdc` (Processing Hub) definitions modules map cleanly to per-namespace deployments. |
| FastAPI gateway | [ADR-005](adr-005-fastapi-gateway.md) | Runs as a Deployment behind the Istio ingress gateway. Still the single entry point. Mesh `AuthorizationPolicy` is defense in depth, not a replacement for the gateway's authN and authZ. |
| Nuts decentralized auth | [ADR-006](adr-006-nuts-node-decentralized-auth.md) | The sidecar pattern fits Kubernetes naturally (one Nuts Node Deployment per DID). The public gRPC port must be excluded from mesh mTLS or set to `PERMISSIVE`. Per-DID rate limiting and backpressure (E6) can move to the Envoy and mesh layer. |
| Dagster execution | ADR-003, ADR-006 | Adopt the `dagster-k8s` run launcher and `k8s_job_executor`. Each run becomes an isolated pod with its own limits. This is new deployment configuration, not new application code. |
| Observability | [Future Features](../development/future-features.md) | Directly enabled. Mesh telemetry plus the planned `/metrics` endpoint plus Grafana give multi-station dashboards and tracing. |
| Security: fine-grained access control, activity logging | [Future Features](../development/future-features.md) | `NetworkPolicy`, RBAC, mesh authorization, and audit-friendly namespaces strengthen the NEN 7513 audit story. The gateway still owns per-query and per-write authorization. |
| Secrets | [Docker guide](../guides/docker.md) | Move from `env_file` to Kubernetes `Secret` objects, optionally an external vault via the Secrets Store CSI driver, as the docker guide already anticipates. |
| Deployment artifacts | `deploy/` | Add `deploy/k8s/` (Helm chart or Kustomize overlays per role). Compose files stay for development. Terraform (`deploy/infra/`) can optionally provision a managed cluster (for example AKS) alongside the existing ACR and storage. |

No planned module is blocked or rewritten. Kubernetes and the mesh add an isolation and operations layer beneath the existing roles, and they make several already planned features (per-run isolation, observability, fine-grained access control, secret management) easier to deliver.

## Alternatives considered

| Alternative | Why not chosen as the primary path |
|---|---|
| Stay on Docker Compose only | Cannot express NetworkPolicy, Pod Security, per-run isolation, RBAC, or mTLS. Insufficient for stations with strict segmentation needs. Kept as the default for development and small stations. |
| Docker Swarm | Adds encrypted secrets but a weaker ecosystem, no real network policy or pod security model, declining adoption. |
| HashiCorp Nomad | Capable scheduler, but smaller healthcare and tooling ecosystem and no built-in network policy without extra components. |
| Linkerd instead of Istio | Lighter and simpler mTLS, less operational overhead. A valid choice when L7 traffic policy and egress control are not required. Recorded as the recommended lighter option. |
| Cilium NetworkPolicy (eBPF) without a full mesh | Strong L3/L4 policy and transparent encryption with less overhead than a sidecar mesh. Viable when service-level mTLS identity and L7 authorization are not needed. |
| Expose services without a mesh, rely on NetworkPolicy only | Simpler, but no automatic mTLS or per-service identity. Acceptable for low-risk stations; insufficient for zero-trust requirements. |

## Consequences

- Operational complexity rises. Not every hospital has Kubernetes expertise, so Compose stays as the default and Kubernetes is opt-in.
- New deployment artifacts are needed under `deploy/k8s/` (Helm or Kustomize), maintained alongside the Compose files.
- Dagster gains a Kubernetes run launcher and executor configuration. Query runs become isolated pods.
- The mesh and the Nuts layer must be reconciled: the Nuts public gRPC port is excluded from mesh mTLS or set to `PERMISSIVE`; the Nuts internal API stays localhost only.
- Datastation and Processing Hub map to separate namespaces with default-deny `NetworkPolicy` and restricted Pod Security. Separate clusters remain the recommendation for hard isolation.
- Secrets move toward Kubernetes `Secret` objects or an external vault, replacing `env_file` in the Kubernetes profile.
- Several planned features (per-run isolation, observability, fine-grained access control, secret management) become easier to implement on this profile.
- The application code defined in ADR-001, ADR-005, and ADR-006 does not change. This is a deployment and packaging decision.
- Istio's ingress gateway replaces Traefik in the Kubernetes profile. Traefik remains in the Compose profile.
- Authentication and authorization gain a third layer (intra-cluster workload identity) underneath the edge and cross-org layers. It is defense in depth and does not replace the gateway's per-query authorization or Nuts credential scope.
- REST plus OpenAPI stays the single external and cross-org API contract. gRPC is allowed only as an internal, in-mesh optimization.
- Verifiable Credentials remain required at the cross-org boundary regardless of how closed the network becomes; the mesh closes only the intra-org boundary.

## Open questions

1. Is Istio's full feature set justified, or is Linkerd or Cilium sufficient for the first stations that need a mesh?
2. Should the first Kubernetes target be a managed cluster (AKS) or on-premise clusters run by the hospitals themselves?
3. Do we package with Helm or Kustomize, and do we maintain one chart with role overlays or two charts?
4. Where do Postgres and DuckLake storage live in the Kubernetes profile: in-cluster with `PersistentVolumeClaim`, or managed services?
5. How is the Nuts Node's persistent data and key material handled under Kubernetes (StatefulSet plus vault-backed keys)?
6. For single-tenant closed deployments where one organization runs both roles in one cluster, do we formally allow mesh identity to replace Nuts on the internal hop, or keep Nuts everywhere for a uniform audit trail?
7. Where do we adopt internal gRPC first (for example code-server to gateway result streaming), and what is the threshold that justifies it over REST?
