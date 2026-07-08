# Nuts Node — Practical Guide for pluginlake

This guide explains how to work with Nuts nodes in the pluginlake development environment.
For an interactive version, open `notebooks/explore_nuts.py` with marimo.

## Quick start

```bash
# Start the Nuts node sidecar
cd deploy/compose
docker compose -f docker-compose.nuts.yaml up -d

# Verify it's running
curl http://127.0.0.1:8081/status
# → OK
```

## Concepts

| Concept | What it is |
|---------|-----------|
| **Subject** | A logical identity on the node, identified by an internal UUID |
| **DID** | The public decentralized identifier (`did:web:...`) associated with a subject |
| **NutsOrganizationCredential** | A Verifiable Credential proving which organization operates a node |
| **Wallet** | Storage of credentials a subject can present to others |
| **Discovery Service** | A directory where nodes register and find each other |
| **DPoP token** | A proof-of-possession access token used for node-to-node authentication |

## API reference (internal, port 8081)

All operations happen via the internal API. This API should never be exposed publicly.

### Create a subject

```bash
curl -X POST http://127.0.0.1:8081/internal/vdr/v2/subject \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:
```json
{
  "subject": "a21e2330-7665-4969-9d5c-ccb5b4abe4b3",
  "documents": [{"id": "did:web:nuts-hub.localhost:iam:f980ede1-..."}]
}
```

### Add OAuth service endpoint

The DID document must advertise the OAuth Authorization Server URL so other nodes can discover it:

```bash
curl -X POST http://127.0.0.1:8081/internal/vdr/v2/subject/<subject-id>/service \
  -H "Content-Type: application/json" \
  -d '{
    "type": "oauth",
    "serviceEndpoint": "https://nuts-hub.localhost/oauth2/<subject-id>"
  }'
```

### Issue a NutsOrganizationCredential

```bash
curl -X POST http://127.0.0.1:8081/internal/vcr/v2/issuer/vc \
  -H "Content-Type: application/json" \
  -d '{
    "issuer": "<your-did>",
    "type": "NutsOrganizationCredential",
    "credentialSubject": {
      "id": "<your-did>",
      "organization": {
        "name": "Demo Ziekenhuis",
        "city": "Utrecht"
      }
    },
    "withStatusList2021Revocation": false,
    "expirationDate": "2027-01-01T00:00:00Z"
  }'
```

Important notes:
- `issuer` and `credentialSubject.id` are the DID from step 1
- `expirationDate` is required when `withStatusList2021Revocation` is false
- In production, a trusted party issues this credential (not self-issued)

### Load credential into wallet

The issued credential is stored in the registry but not automatically in the wallet.
You must explicitly load it:

```bash
curl -X POST http://127.0.0.1:8081/internal/vcr/v2/holder/<subject-id>/vc \
  -H "Content-Type: application/json" \
  -d '<full-credential-json-from-previous-step>'
```

Returns `204 No Content` on success.

### Register at the discovery service

```bash
curl -X POST http://127.0.0.1:8081/internal/discovery/v1/pluginlake-network/<subject-id> \
  -H "Content-Type: application/json" \
  -d '{}'
```

Prerequisites:
- The wallet must contain the credentials required by the discovery service definition
- The Nuts node must be able to reach the discovery server endpoint

### Search the discovery service

```bash
curl "http://127.0.0.1:8081/internal/discovery/v1/pluginlake-network?credentialSubject.organization.city=*"
```

Returns all registered nodes matching the query. Use `*` as a wildcard.

### Request an access token (node-to-node)

When a hub wants to call a station, it needs the station's OAuth Authorization Server URL (from the discovery service `authServerURL` field):

```bash
curl -X POST http://127.0.0.1:8081/internal/auth/v2/<subject-id>/request-service-access-token \
  -H "Content-Type: application/json" \
  -d '{
    "authorization_server": "https://nuts-station.localhost/oauth2/<station-subject-id>",
    "scope": "pluginlake-data-access"
  }'
```

Returns a DPoP-bound access token:
```json
{
  "access_token": "VOKz_QMvwH67nruDBs3ByDCq2ihDPh-u59UZDf6ekkc",
  "token_type": "DPoP",
  "expires_in": 900,
  "scope": "pluginlake-data-access"
}
```

### Introspect a token (receiving side)

When a station receives a request from a hub, it introspects the token:

```bash
curl -X POST http://127.0.0.1:9081/internal/auth/v2/accesstoken/introspect \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=<access-token>"
```

Returns the introspected claims:
```json
{
  "active": true,
  "client_id": "https://nuts-hub.localhost/oauth2/<hub-subject-id>",
  "iss": "https://nuts-station.localhost/oauth2/<station-subject-id>",
  "scope": "pluginlake-data-access",
  "organization_name": "PLUGIN Research Hub",
  "organization_city": "Utrecht"
}
```

## Configuration files

| File | Purpose |
|------|---------|
| `config/nuts/hub/nuts.yaml` | Hub-specific config (discovery server enabled) |
| `config/nuts/station/nuts.yaml` | Station-specific config (discovery client only) |
| `config/nuts/discovery/pluginlake-network.json` | Discovery service definition |
| `config/nuts/policy/pluginlake-data-access.json` | Access token policy (scope → credential requirements) |
| `config/traefik/traefik.yaml` | Traefik static config (TLS entrypoint) |
| `config/traefik/dynamic.yaml` | Traefik dynamic routing (hostname → Nuts node) |
| `deploy/compose/docker-compose.nuts.yaml` | Docker Compose overlay for single-node sidecar |
| `deploy/compose/docker-compose.traefik.yaml` | Docker Compose overlay for Traefik |

## Architecture in development

```
Host machine
├── scripts/generate-dev-certs.sh     → generates .data/traefik/certs/
│
├── docker compose (two-node test network)
│   ├── traefik                       → :443 (TLS termination, *.localhost routing)
│   ├── nuts-hub                      → :8081 internal API
│   │   └── Discovery server, OAuth AS for hub subject
│   ├── nuts-station                  → :9081 internal API
│   │   └── OAuth AS for station subject
│   ├── hub (FastAPI stub)            → :8000
│   └── station (FastAPI stub)        → :9090
│
└── .data/
    ├── traefik/certs/                → CA + wildcard cert for *.localhost
    └── nuts/                         → Nuts node data (single-node dev)
```

Traefik provides TLS so that `did:web` resolution works between nodes (RFC requires HTTPS).
Nodes resolve each other's DID documents via `https://nuts-{hub,station}.localhost/iam/{did-path}/did.json`.

## Two-node network test

For testing the full hub↔station flow:

```bash
# Generate TLS certificates (first time only, from repo root)
scripts/generate-dev-certs.sh

# Start the network
cd tests/integration/nuts-network
docker compose up -d

# Bootstrap DIDs, credentials, discovery, and test token exchange
./bootstrap.sh
```

The bootstrap script performs the full lifecycle:
1. Creates subjects (DIDs) on each node
2. Adds OAuth service endpoints to each DID document
3. Issues NutsOrganizationCredentials
4. Loads credentials into wallets
5. Registers both nodes at the discovery service
6. Verifies mutual discovery
7. Tests token exchange (hub requests access token, station introspects it)

## Common issues

**Permission denied on `.data/nuts/`**
The compose runs as your user (`${UID:-1000}`). If you see permission errors, ensure the directory is owned by your user:
```bash
rm -rf .data/nuts && mkdir -p .data/nuts
```

**Discovery registration fails with "missing credentials"**
The wallet doesn't have the required credential. Make sure you:
1. Issued the credential (`POST /internal/vcr/v2/issuer/vc`)
2. Loaded it into the wallet (`POST /internal/vcr/v2/holder/{subject}/vc`)

**Discovery registration fails with TLS/DNS error**
The discovery endpoint in `pluginlake-network.json` uses `https://nuts-hub.localhost/discovery/pluginlake-network`.
This requires Traefik to be running with valid dev certificates.
Run `scripts/generate-dev-certs.sh` if you haven't already.

**Token exchange fails with "url must contain scheme and host"**
The target node's DID document is missing an OAuth service endpoint.
Add one with `POST /internal/vdr/v2/subject/{id}/service` (type: `oauth`, serviceEndpoint: the OAuth2 URL).
