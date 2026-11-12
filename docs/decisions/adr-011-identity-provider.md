# ADR-011: Identity provider

- **Status:** Proposed
- **Date:** 2026-11-10
- **Authors:** pluginlake team

## TL;DR

Every web UI sits behind Traefik and oauth2-proxy with an OIDC provider.
Zitadel is chosen for both Data Stations and Processing Hubs because it is light and already works, on the assumption that we run the unmodified images.
Keycloak is the fallback if a license or footprint problem appears, and the [spike](#spike) shows it works.

## Context

The web UIs (API, Dagster, dashboard, Marquez, Prometheus) were published without authentication.
Story #127 asks for a reverse proxy with forward auth, and ADR-008 (open question 11) leaves the OIDC provider open.
This ADR covers the human logins of boundary 1 in ADR-008.
Access between stations stays with Nuts and DSP (ADR-006, ADR-008).

The load differs per role, and both roles use the same components:

- A Data Station has a few users for control, maintenance and configuration.
- A Processing Hub has complex logins: several organizations, federation with their identity providers and fine-grained access.
- Later, the provider has to help decide which containers and queries a user or project may run, based on data contracts.
The contract itself (DSP, ODRL) stays the source of truth.
The provider supplies identities, groups and claims.

Stations run on a VM with 64 GB of RAM or in a cluster, and the RAM is meant for compute, so the provider should stay small and be capped.

## Alternatives

| | Zitadel | Authentik | Keycloak |
|---|---|---|---|
| Docs | [zitadel.com/docs](https://zitadel.com/docs) | [docs.goauthentik.io](https://docs.goauthentik.io/) | [keycloak.org/documentation](https://www.keycloak.org/documentation) |
| License | AGPL-3.0 | MIT, but `authentik/enterprise/` needs a paid subscription | Apache-2.0, no paid tier |
| Containers | API and login UI | Server and worker | 1 |
| Idle memory, reported | 214 MiB | 715 MiB | 539 MiB |
| OIDC app from config | No, Management API (our code) | Yes, blueprints | Yes, realm import |
| Forward auth | oauth2-proxy | Built-in outpost | oauth2-proxy |
| Fine-grained access | Roles and claims | Policies per application | Roles, groups and [authorization services](https://www.keycloak.org/docs/latest/authorization_services/) |
| Login cost, reported | 997 ms CPU | 1,187 ms CPU | 72 ms CPU |

Numbers come from an [independent measurement](https://computingforgeeks.com/keycloak-vs-authentik-vs-zitadel-vs-authelia/) and are indicative.
Authentik's paid features ([list](https://docs.goauthentik.io/enterprise/enterprise-features/)) are an external IdP embedded in a flow, enhanced audit logging and password history.
Login with Entra ID, Google or SURFconext works through its free sources.

## Decision

Use Zitadel for Data Stations and Processing Hubs, behind [Traefik forward auth](https://doc.traefik.io/traefik/middlewares/http/forwardauth/) and [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/).
It has the smallest footprint (about 174 MiB measured) and the current compose stack already runs it.
Authentik drops out as the heaviest, with the slowest logins and the longest upgrade outage.

Zitadel is AGPL-3.0, so the choice rests on 1 assumption: we run the unmodified images as a separate container and talk to it only over OIDC and HTTP.
That is also the view of our architect.
Any patch or fork would have to be published, and code of ours that imports Zitadel code would fall under the AGPL.
Trivy does not flag the license, because it cannot read licenses from the Go binary, so the scan is no evidence.
Our security officer could not say whether the central license policy (permissive licenses only) covers third-party containers.

Keycloak (Apache-2.0) is the fallback if a hospital or a policy rejects AGPL software, or if the clustering or the features of Zitadel fall short.
The spike shows that it works with the same oauth2-proxy and Traefik setup.

To keep switching cheap, the rest of the stack only depends on standard OIDC:

- Applications and oauth2-proxy know an issuer URL, a client id and a client secret, nothing provider-specific.
- Access is based on a `groups` claim that oauth2-proxy checks per application with `allowed_groups`.
  Zitadel produces the claim from project roles by calling the small service `zitadel-groups-hook` (Actions v2, fail closed), whose target `pluginlake-init` creates.
- Provisioning of the client, redirect URIs and first admin is limited to `pluginlake-init`, which is the only code that changes when the provider changes.
- No code of ours calls the Zitadel API after the bootstrap. Zitadel only calls the groups hook.

The setup is described in the [Edge](../guides/docker.md#edge) section of the Docker guide.

### Why we accept the AGPL

The [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html) applies to Zitadel and to works based on it, not to separate programs that talk to it.
We reason that running the unmodified image as its own container and calling it over OIDC and HTTP is use, not modification.
Our own code stays Apache-2.0 and the AGPL asks nothing of it.
The alternatives cost more RAM (Keycloak and Authentik), and Authentik keeps some features behind a paid tier.
The reasoning has not been checked by a lawyer.

| We may | We may not, without publishing the source or switching provider |
|---|---|
| Run the unmodified image on stations and hubs, also for hospitals | Patch or fork Zitadel and offer that version to users |
| Configure it and use its API from `pluginlake-init` | Import Zitadel code or libraries into our code |
| Ship the image reference and the license notice with a release | Copy Zitadel source files into our repository |
| Theme the login with the documented settings | Offer a modified Zitadel as a service under our name |

A patch we would want to keep private is therefore a reason to switch to Keycloak.
If a hospital or a policy rejects AGPL software, we also switch.

## Consequences

- Smallest footprint of the options (about 174 MiB against about 510 MiB for Keycloak), which leaves the RAM for compute.
- AGPL-3.0 is acceptable while we run it unmodified, but a customer or auditor may still reject it, and then we switch to Keycloak.
- Switching means a new provisioning step in `pluginlake-init` (a realm import for Keycloak), new compose services and users re-created in the new provider.
- Zitadel reads its database and admin passwords from YAML files (`--config`, `--steps`), so they are mounted as secrets like the rest of the stack, and the login UI sets its cookie secret from a file in its entrypoint.
- Users, their passwords and their access live in Zitadel, and later also in contracts. Our configuration holds no user data.
- The only user we create is the first admin, with a generated password that Zitadel always forces to change at the first login.
- Machine users of Zitadel (`pluginlake-init` and the login client) authenticate the bootstrap.
  Machine users can also serve as a first trust between a hub and a data station, until the Nuts decision is made.
- Fine-grained access follows the data contracts in our own layer (DSP, ODRL), with the provider supplying identities, groups and claims.
- Access starts per service or application, and profiles follow later on top of that.

## Spike

Timebox: 1 day for the setup and measurements, half a day for the write-up.
Build the same stack for Keycloak and Zitadel (Traefik, provider, own Postgres role, 1 protected host), and test Authentik only on provisioning and secrets.

| Criterion | Question |
|---|---|
| Footprint | Memory and CPU per container, idle and after 50 logins, with a capped Keycloak heap (for example `-Xmx512m`) |
| Provisioning | Can the OIDC application be created from configuration alone? |
| Federation | Does a login via Entra ID, Google or SURFconext reach the protected host, without a paid feature? |
| Proxy fit | Does it work with Traefik forward auth and the websockets of Dagster and the dashboard? |
| Audit | Are login events (who, when, from where) free, retained for a configurable period and exportable? |
| Machine tokens | Client credentials for API clients, audience checks by oauth2-proxy, rotation of client secrets and signing keys |
| Secrets | Can database, admin and optional SMTP passwords come from files (`/run/secrets`) instead of environment variables? |
| Groups | Does a groups claim limit access per host with `--allowed-group`? |
| Clustering | Do 2 replicas work behind Traefik or an Ingress without sticky sessions, and do logins survive losing 1 pod? |
| Operations | Upgrades, backup restore and key rotation |
| Nuts | Can it coexist with Nuts and DPoP paths on 1 hostname (#127)? |

SMTP is optional: it is only needed for password mails and alerts when a station uses local accounts, not when it logs in through an external provider.

Outcome: this ADR becomes Accepted, or is superseded by an ADR for the winning provider, or the edge gets a provider interface so stations can choose.

## Results

Run on 2026-11-10 with Keycloak 26.4.7 and Postgres 17 in Docker on a laptop, scripts in the local `.agents/memory/spike/`.
Zitadel numbers come from the running compose stack.
Authentik was not run.

| Criterion | Keycloak | Zitadel |
|---|---|---|
| Footprint | 510 MiB idle and 617 MiB after 50 logins, heap capped at 512 MiB, started in 24 s | 174 MiB idle (API 90, login UI 84) |
| Provisioning | Realm import: realm, clients, users, groups and the groups mapper from 1 JSON file, no own code | Management API calls from `pluginlake-init` |
| Secrets | Database and bootstrap admin password from a mounted `keycloak.conf` (0400), no environment variables | Only as environment variables (`env_file`) |
| Federation | Login through a second OIDC provider worked, the user is created on first login | Not tested |
| Groups | `groups` claim in the token per user, usable with `--allowed-group` | Project roles plus the Actions v2 call target `groups-claim` (project role assertion on) give a `groups` claim. A user with only the role `dagster` opens Dagster and gets 403 on the other applications |
| Machine tokens | Client credentials work, tokens last 300 s, new client secret invalidates the old one, adding a signing key publishes it in the JWKS next to the old key | Not tested |
| Audit | Login events with user, IP and time are free, retention is configurable, the admin API lists them | Event store (not tested) |
| Clustering | 2 replicas without sticky sessions: a refresh token from replica 1 works on replica 2, and logins keep working after stopping replica 1 | Not tested |
| Proxy fit | Behind Traefik forward auth and oauth2-proxy: anonymous requests and websocket upgrades get a 302, a member of `station-admins` gets 200, the `X-Auth-Request-*` headers arrive and the websocket upgrade returns 101, a member of `viewers` gets 403 | Not tested |

Gotchas found:

- A realm import with its own `clientScopes` block drops the built-in scopes (`openid`, `profile`, `email`).
Put the groups mapper on the client instead.
- Imported users need a first and last name, otherwise the login fails with "Account is not fully set up".
- Tokens carry `aud=account`, so oauth2-proxy audience checks need an audience mapper on the client.
- A brokered user gets no groups.
Add a mapper or a default group per upstream provider.
- Clients and the upstream client secret sit in the realm JSON.
Check if the vault can supply them.
- The hostname must be fixed (`--hostname`), otherwise tokens from one replica are rejected by another because the issuer differs.
- oauth2-proxy adds a `groups` scope when `--allowed-group` is set, which Keycloak does not know.
Set `--scope="openid email profile"` explicitly.
- oauth2-proxy must start after Keycloak is healthy, otherwise OIDC discovery fails.
- A service-account token has no groups claim and is denied by `--allowed-group`.
Machine clients need a groups or audience mapper on their client.
- A realm is only imported when it does not exist yet, so later changes need the admin API or a partial import.

Not tested and still open: federation with a real Entra ID or SURFconext tenant, Nuts and DPoP paths, upgrade and backup restore, machine clients passing `--allowed-group` (groups or audience mapper).

Authentik was not run and stays dropped.
Access starts per service or application, with profiles added later on top of the groups.

The results show that Keycloak works as a fallback.
The status stays Proposed until the open items are done and the license assumption is confirmed.
