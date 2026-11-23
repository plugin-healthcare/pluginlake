# ADR-012: Core platform and deployment

- **Status:** Proposed
- **Date:** 2026-11-17
- **Authors:** pluginlake team

## TL;DR

The core platform (API, Dagster, Marquez, Postgres and the edge) is the same on every node, and the deployment is everything around it that depends on where the node runs.
A node runs on one of three tiers: Docker Compose on a VM, Kubernetes on a VM, or a Kubernetes cluster on bare metal or at a provider.
Docker Compose is the first supported tier and `pluginlake.toml` is its only interface, so an operator never has to edit the compose files.
Components that exist only because of a runtime belong to that runtime: cAdvisor is a Compose component, and on Kubernetes the kubelet already serves the same metrics.
What is still open is how far the core supports Kubernetes, who owns the edge on each tier and how the network around a node is limited.

## Context

[ADR-009](adr-009-core-project-plugin-architecture.md) separates the core from the projects that run on it.
Nodes are operated by hospitals and other organisations, on infrastructure that we do not control, so the platform has to run in more than one place without per-node changes to its code.

Two forces pull against each other:

- An operator wants to configure a node, not to clone the repository and edit compose files, because that makes every upgrade a merge.
- Environments differ in what they already provide: a bare-metal VM has no container metrics, no load balancer and no managed store, while a managed cluster has all of them.

Without a boundary, either the core ends up with choices for every environment, or the operator ends up maintaining a fork.

## Decision

### Runtime tiers

| Tier | Who runs what | Container metrics | Metrics store |
|---|---|---|---|
| 1. Docker Compose on a VM | The operator runs the VM and Docker | Our `cadvisor` container | Local Prometheus, optional |
| 2. Kubernetes on a VM (k3s, kubeadm) | One node runs control plane and workloads | The kubelet serves cAdvisor on `/metrics/cadvisor` | Own Prometheus, optional |
| 3a. Cluster on bare metal or own VMs | The operator runs all nodes, storage, load balancer and upgrades | The kubelet | Own Prometheus |
| 3b. Managed cluster | The provider runs the control plane and often the nodes, upgrades and load balancer | The kubelet | Provider monitoring or own Prometheus |

Tier 2 is the one-node case of tier 3a: the manifests are the same and the setup around them differs (storage class, load balancer, resilience).
Docker Compose has no managed variant, so it is always a VM that the operator manages.

### What is core and what is deployment

A component belongs to the core when every node needs it and its behaviour does not depend on the runtime.
A component belongs to the deployment when it only exists to bridge a difference between runtimes.

| Core (same on every tier) | Deployment (per tier) |
|---|---|
| API, Dagster, Marquez, Postgres | Compose files and the Kubernetes manifests or charts |
| The edge behaviour: sign-in, roles, routes | Who runs the proxy, certificates and domain |
| The metrics the components expose | How container metrics and a metrics store are provided |
| The settings in `pluginlake.toml` | How those settings reach the runtime |

### One interface for the operator

An operator configures a node in `pluginlake.toml`, and `pluginlake setup` turns that into what the runtime needs (for Compose: the data folder, the secrets and `compose.env`).
Every option that an operator may need must therefore be a setting, and a request to edit a compose file is a missing setting.
Secrets are files that the operator or a secret manager provides, so the same contract works where a secret store exists and where it does not.

### Components per runtime

Some components are tied to a runtime and are not part of the other tiers:

- cAdvisor runs as a container on Compose only.
  On Kubernetes the kubelet serves the same metrics.
- A local Prometheus is optional on every tier, so a local metrics store remains possible without central monitoring ([ADR-010](adr-010-station-monitoring-prometheus.md)).
- Identity stays the same on every tier: Zitadel with the groups hook, and authentication at the edge ([ADR-011](adr-011-identity-provider.md)).

### Network exposure

The proxy is never the only layer that is exposed to the internet, and each layer assumes that the others can fail:

| Layer | Core (same everywhere) | Deployment (flavours) |
|---|---|---|
| Network | A bind address and an allowlist as settings | Firewall, VPN, cloud security group |
| Edge | Allowlist, rate limiting, security headers, structured access logs | Who runs the proxy and certificates |
| Behaviour | The access logs | CrowdSec, fail2ban or the organisation's own intrusion detection |
| Identity | Sign-in and roles on every route | The identity provider's own hosting |

The core provides the same settings and logs on every node, and the deployment decides which of the surrounding tools are used.

### Differences that matter on Kubernetes

- Storage: the bind-mounted data folders become persistent volumes. Managed clusters have storage classes, bare metal needs its own storage layer.
- Ingress and TLS: the edge runs as an ingress controller, with a load balancer from the provider or from the operator.
- Secrets: managed clusters can use the provider's store, bare metal uses Kubernetes secrets or a separate vault.
- Operations: upgrades, backups and node failures are the operator's on bare metal.

## Open questions

- Does the core support tier 1 only for now, with tier 2 as the first Kubernetes target?
- Do `pluginlake setup` and `pluginlake.toml` stay the interface on Kubernetes, or do they only apply to Compose?
- Who owns the edge (proxy, TLS, domain and sign-in) on each tier, and is that a contract between the core and the deployment?
- How is the network around a node limited: the bind address of the proxy, an allowlist, and what the operator is expected to arrange in the firewall?
- Is a reactive blocker such as CrowdSec part of the core, or an option per deployment?
- Which components must keep working without access to the Docker socket?
- What do we maintain ourselves, what is best effort, and what is left to the operator?
- How do we test a tier without a cloud?

## Consequences

- Operators never fork the compose files: a missing setting is a gap in the core.
- Runtime-specific components can be added or dropped per tier without changing the core, which keeps the Compose stack from carrying things Kubernetes already provides.
- The core carries the cost of a settings model that has to be translated per runtime.
- Until the open questions are decided, only tier 1 is covered by tests and documentation.

## References

The layers above are a simplified reading of these sources.

- [CNCF Cloud Native Glossary, Zero Trust Architecture](https://glossary.cncf.io/zero-trust-architecture/) as a plain-language explanation
- [NIST SP 800-207, Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final)
- [NCSC-NL](https://www.ncsc.nl/) guidelines for TLS, zero trust and web applications
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks) for Docker and Kubernetes
- [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- NEN 7510, NEN 7512 and NEN 7513 (see [NEN](https://www.nen.nl/)) and ISO/IEC 27002
