# Getting started

This guide starts a complete pluginlake node on your own machine: the edge with Traefik, oauth2-proxy and Zitadel, plus Dagster, the API, lineage and monitoring.
The node is an empty platform instance without data or assets of its own.
A project adds its assets, routes and data on top, see [Deploying a station](deploying-a-station.md).
To build assets with the development tooling, see the [Titanic tutorial](../development/titanic-tutorial.md).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose, for example Docker Desktop, Colima or Docker Engine
- [just](https://github.com/casey/just)
- [mkcert](https://github.com/FiloSottile/mkcert), only for a `.localhost` domain, to get a locally trusted certificate. You do not need it when you use your own domain with a certificate from a certificate authority.
- A Docker Hub account with `docker login dhi.io` done once, because the images are built on hardened base images (see [Docker](docker.md#hardened-base-images))

On macOS with Colima, keep the checkout under your home folder, because Colima only shares that folder with the containers.
The node data is stored in `.pluginlake/` inside the checkout (or in `PLUGINLAKE_HOME` when set).

## 1. Start the node

```bash
git clone https://github.com/plugin-healthcare/pluginlake.git
cd pluginlake
just up
```

`just up` prepares the node from `pluginlake.toml` (folders, secrets and `compose.env` in `.pluginlake/`), creates a certificate for the `.localhost` domain in `[node]`, then builds and starts all containers.
The first start takes a few minutes, because the images are built and Zitadel is provisioned.
Add `-d` to run it in the background.

While the node is starting, the console shows a start-up page that refreshes by itself.

## 2. Sign in

Open [https://console.pluginlake.localhost](https://console.pluginlake.localhost) and sign in as the first admin:

| Field | Value |
|-------|-------|
| Login name | `admin@zitadel.auth.pluginlake.localhost` |
| Password | `.pluginlake/secrets/zitadel_admin_password` |

Zitadel asks you to choose a new password at the first sign-in.
Store it in a password manager, because the file keeps the initial password only.

## 3. Use the console

The console is the start page of the node.
Its sidebar links to the other applications, and only shows the ones your roles give access to.

| Application | Address |
|-------------|---------|
| Console | `https://console.pluginlake.localhost` |
| Dagster | `https://dagster.pluginlake.localhost` |
| Lineage (Marquez) | `https://marquez.pluginlake.localhost` |
| Metrics (Prometheus) | `https://prometheus.pluginlake.localhost` |
| API documentation | `https://api.pluginlake.localhost/docs` |

You sign in once for all of them.
Use **Sign out** in the sidebar to end the session.

## 4. Stop the node

```bash
just down
```

The data stays in `.pluginlake/`, so the next `just up` continues where you left off.
To start from scratch, run `just down` and remove `.pluginlake/` afterwards.
This deletes all data of the node.

## Production

Set `domain` under `[node]` in `pluginlake.toml` to your own domain and run `just up`.
For developing the platform itself, use the `just dev-*` recipes instead (see the [Docker guide](docker.md)).
The stack does not provision a production certificate yet, so Traefik needs a certificate for your domain before oauth2-proxy can reach Zitadel.
See the [Docker guide](docker.md#edge) for the edge, the roles and the secrets.
