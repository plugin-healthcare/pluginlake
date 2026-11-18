# ADR-011: Identity provider

- **Status:** Proposed
- **Date:** 2026-11-10
- **Authors:** pluginlake team

## TL;DR

Web UIs are protected at the edge by Traefik forward auth and oauth2-proxy, which log users in with an OIDC provider, and API clients can also call with a valid token.
We choose Zitadel for both Data Stations and Processing Hubs because it is light and already works, on the assumption that we run the unmodified images.
The trade-off is an extra service, the `zitadel-groups-hook`, which Keycloak does not need because it maps groups itself.
Keycloak can replace Zitadel when a license or footprint problem appears, and the [spike](#spike) shows that it works behind the same edge.

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

Keycloak (Apache-2.0) can replace Zitadel if a hospital or a policy rejects AGPL software, or if Zitadel falls short on clustering or features. A spike decides how then.

To keep switching cheap, the rest of the stack only depends on standard OIDC:

- Applications and oauth2-proxy know an issuer URL, a client id and a client secret, nothing provider-specific.
- Access is based on a `groups` claim that oauth2-proxy checks per application with `allowed_groups`.
  Zitadel produces the claim from project roles by calling the small service `zitadel-groups-hook` (Actions v2, fail closed).
- Provisioning of the client, redirect URIs and first admin is limited to `pluginlake-init`, which is the only code that changes when the provider changes.

The setup is described in the [Edge](../guides/docker.md#edge) section of the Docker guide.

### Why a separate groups hook

Zitadel only emits its roles as an object, while oauth2-proxy needs a list, so a small service has to translate them.
This is the route Zitadel documents for oauth2-proxy.

- Access is checked at the edge, because most components (Dagster, Marquez, Prometheus) are not built by us and cannot check roles themselves.
- The hook is its own stateless container, so sign-in does not depend on the API, Postgres or DuckLake, and it is only reachable on the internal network.
- It is not part of `pluginlake-init`, because that container exits after startup while Zitadel calls the hook on every token.
- oauth2-proxy stays instead of our own login code, because OIDC login, sessions and refresh are better left to a maintained project.
- If the hook is down nobody can sign in, which is the safe failure.
- Validating the token in our own API is a later addition and does not replace the edge check.

### Session lifetime

A session at the edge ends after 30 minutes without use, and the user enters their credentials again 12 hours after signing in.
The 12 hours follow the reauthentication limit of NIST SP 800-63B for AAL2, the level that fits access to health data.
The 30 minutes without use of AAL2 only apply to the edge session, so nobody is signed out in the middle of their work.

- oauth2-proxy refreshes the session with Zitadel every 5 minutes, so a removed role takes effect within those minutes instead of when the cookie expires.
- The 30 minutes are the cookie lifetime of oauth2-proxy, which starts again at every refresh.
- oauth2-proxy cannot limit the total length of a session, so the 12 hours are the lifetime of the refresh token in Zitadel, counted from when Zitadel issued it at sign-in; after that the refresh fails and oauth2-proxy sends the user to Zitadel again.
- A browser tab that polls in the background never reaches the 30 minutes, so for that tab the 12 hours are the only limit.
- Zitadel keeps its own sign-in, by default for 10 days after a password check. `pluginlake-init` sets the check lifetimes of the login policy of the instance to the same 12 hours, so at the end of the 12 hours the user enters their credentials again. An organization with a login policy of its own does not inherit these lifetimes.
- After 30 minutes without use, Zitadel signs the user in again without credentials, so nobody loses their work. The idle limit only shortens the time in which a stolen session cookie of the edge can be used.
- Such a sign-in gives a new refresh token of 12 hours, and Zitadel does not end it together with its own sign-in. A user who returns just before their 12 hours end can therefore keep working for almost 24 hours. We accept this edge case, because shorter lifetimes would ask everyone for their password more often.

## Consequences

- Smallest footprint of the options (about 174 MiB against about 510 MiB for Keycloak), which leaves the RAM for compute.
- The price of Zitadel is the extra `zitadel-groups-hook`: about 100 lines of our own code and 1 more container to run, monitor and keep available, because nobody can sign in while it is down. Keycloak has a built-in groups mapper and needs neither.
- A customer or auditor may still reject the AGPL, and then we switch to Keycloak: a realm import instead of the provisioning in `pluginlake-init`, new compose services and users re-created.
- Users and their access live in Zitadel, and later also in contracts. Our configuration holds no user data, only a first admin with a generated password that is forced to change at the first login.
- This ADR describes the edge for Docker Compose. Who owns the edge (proxy, TLS, domain and sign-in) on Kubernetes and on a managed cluster, and how the network around it is limited, is not decided here.
- Fine-grained access follows the data contracts in our own layer (DSP, ODRL), with the provider supplying identities, groups and claims.
- Access starts per service or application, and profiles follow later on top of that.

## Spike

The spike built the same stack for Keycloak and Zitadel (Traefik, provider, own Postgres role, 1 protected host) and compared footprint, provisioning, federation, proxy fit, groups, machine tokens, audit, secrets and clustering.
Authentik was not run and stays dropped.
Run on 2026-11-10 with Keycloak 26.4.7 and Postgres 17 in Docker on a laptop.
Zitadel numbers come from the running compose stack.

### Results

| Criterion | Keycloak | Zitadel |
|---|---|---|
| Footprint | 510 MiB idle, 617 MiB after 50 logins, heap capped at 512 MiB | 174 MiB idle (API 90, login UI 84) |
| Provisioning | Realm import from 1 JSON file, no own code | Management API calls from `pluginlake-init` |
| Federation | Login through a second OIDC provider worked | Not tested |
| Groups | Native groups with a mapper that adds the `groups` claim | No native groups: an Actions v2 target (`zitadel-groups-hook`) turns the flat project roles into a `groups` claim |
| Clustering | 2 replicas without sticky sessions, logins survive losing 1 | Not tested |

Keycloak also worked behind Traefik forward auth and oauth2-proxy, including websockets, and kept database and admin passwords in a mounted file.
