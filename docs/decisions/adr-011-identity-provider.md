# ADR-011: Identity provider

- **Status:** Proposed
- **Date:** 2026-11-10
- **Authors:** pluginlake team

## TL;DR

Every web UI sits behind Traefik and oauth2-proxy with an OIDC provider.
Zitadel is chosen for both Data Stations and Processing Hubs because it is light and already works, on the assumption that we run the unmodified images.
Keycloak is the fallback if a license or footprint problem appears, and the [spike](#spike) shows it works.

## Context

The web UIs (API, console, Dagster, Marquez, Prometheus) were published without authentication.
Story #127 asks for a reverse proxy with forward auth, and ADR-008 (open question 11) leaves the OIDC provider open.
This ADR covers the human logins of boundary 1 in ADR-008.
Access between stations stays with Nuts and DSP (ADR-006, ADR-008).

A Data Station has few users, a Processing Hub has several organizations with federated logins and fine-grained access, and both run the same components.
Later the provider has to help decide which containers and queries a user or project may run.
The data contract (DSP, ODRL) stays the source of truth, and the provider only supplies identities, groups and claims.
Stations keep their RAM for compute, so the provider should stay small.

## Alternatives

| | [Zitadel](https://zitadel.com/docs) | [Authentik](https://docs.goauthentik.io/) | [Keycloak](https://www.keycloak.org/documentation) |
|---|---|---|---|
| License | AGPL-3.0 | MIT, `authentik/enterprise/` is paid | Apache-2.0 |
| Idle memory, reported | 214 MiB | 715 MiB | 539 MiB |
| OIDC app from config | No, Management API | Yes, blueprints | Yes, realm import |
| Forward auth | oauth2-proxy | Built-in outpost | oauth2-proxy |

Numbers come from an [independent measurement](https://computingforgeeks.com/keycloak-vs-authentik-vs-zitadel-vs-authelia/) and are indicative.

## Decision

Use Zitadel for Data Stations and Processing Hubs, behind [Traefik forward auth](https://doc.traefik.io/traefik/middlewares/http/forwardauth/) and [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/).
It has the smallest footprint (about 174 MiB measured) and the current compose stack already runs it.
Authentik drops out as the heaviest, with the slowest logins and the longest upgrade outage.

Zitadel is AGPL-3.0, so the choice rests on 1 assumption: we run the unmodified image as a separate container and talk to it only over OIDC and HTTP, which is also the view of our architect.
The AGPL applies to Zitadel and works based on it, not to separate programs that talk to it, and our own code stays Apache-2.0.
A patch or fork would have to be published, and code of ours that imports Zitadel code would fall under the AGPL, so a patch we want to keep private is a reason to switch.
Trivy cannot read licenses from the Go binary, so the scan is no evidence, and the security officer could not say whether the central license policy covers third-party containers.
A lawyer has not checked this reasoning.

Keycloak (Apache-2.0) is the fallback if a hospital or a policy rejects AGPL software, or if Zitadel falls short on clustering or features.

To keep switching cheap, the rest of the stack only depends on standard OIDC:

- Applications and oauth2-proxy know an issuer URL, a client id and a client secret, nothing provider-specific.
- Access is based on a `groups` claim that oauth2-proxy checks per application with `allowed_groups`.
  Zitadel produces the claim from project roles by calling the small service `zitadel-groups-hook` (Actions v2, fail closed).
- Provisioning of the client, redirect URIs and first admin is limited to `pluginlake-init`, which is the only code that changes when the provider changes.

The setup is described in the [Edge](../guides/docker.md#edge) section of the Docker guide.

## Consequences

- Smallest footprint of the options (about 174 MiB against about 510 MiB for Keycloak), which leaves the RAM for compute.
- A customer or auditor may still reject the AGPL, and then we switch to Keycloak: a realm import instead of the provisioning in `pluginlake-init`, new compose services and users re-created.
- Users and their access live in Zitadel, and later also in contracts. Our configuration holds no user data, only a first admin with a generated password that must change at the first login.
- Fine-grained access follows the data contracts in our own layer (DSP, ODRL), with the provider supplying identities, groups and claims.
- Access starts per service or application, and profiles follow later on top of that.

## Spike

The spike built the same stack for Keycloak and Zitadel (Traefik, provider, own Postgres role, 1 protected host) and compared footprint, provisioning, federation, proxy fit, groups, machine tokens, audit, secrets and clustering.
Authentik was not run and stays dropped.
Run on 2026-11-10 with Keycloak 26.4.7 and Postgres 17 in Docker on a laptop, scripts in the local `.agents/memory/spike/`.
Zitadel numbers come from the running compose stack.

### Results

| Criterion | Keycloak | Zitadel |
|---|---|---|
| Footprint | 510 MiB idle, 617 MiB after 50 logins, heap capped at 512 MiB | 174 MiB idle (API 90, login UI 84) |
| Provisioning | Realm import from 1 JSON file, no own code | Management API calls from `pluginlake-init` |
| Federation | Login through a second OIDC provider worked | Not tested |
| Groups | `groups` claim per user, works with `--allowed-group` | Project roles plus an Actions v2 target give a `groups` claim, and a user with only the role `dagster` gets 403 on the other applications |
| Clustering | 2 replicas without sticky sessions, logins survive losing 1 | Not tested |

Keycloak also worked behind Traefik forward auth and oauth2-proxy, including websockets, and kept database and admin passwords in a mounted file.

Gotchas of the Keycloak fallback:

- A realm import with its own `clientScopes` block drops the built-in scopes, so put the groups mapper on the client.
- Tokens carry `aud=account`, so audience checks need an audience mapper, and service accounts need a groups or audience mapper to pass `--allowed-group`.
- A brokered user gets no groups, so add a mapper or a default group per upstream provider.
- The hostname must be fixed (`--hostname`), otherwise replicas reject each other's tokens.
- oauth2-proxy needs `--scope="openid email profile"` and must start after Keycloak is healthy.

Not tested and still open: federation with a real Entra ID or SURFconext tenant, Nuts and DPoP paths on 1 hostname (#127), upgrade and backup restore.
The results show that Keycloak works as a fallback.
The status stays Proposed until the open items are done and the license assumption is confirmed.
