"""Nuts Node — Identity & Discovery Demo

Interactive walkthrough of the Nuts node API for pluginlake.
Demonstrates creating a DID, issuing credentials, and registering
at the discovery service.

Requires the Nuts node sidecar running:
    cd deploy/compose && docker compose -f docker-compose.nuts.yaml up -d
"""

import marimo

__generated_with = "0.23.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Nuts Node — Identity & Discovery Demo

    This notebook demonstrates the practical API interactions with a Nuts node.
    It walks through the full lifecycle of a pluginlake node joining the network:

    1. **Health check** — verify the Nuts node is running
    2. **Create a subject** — generate a DID (decentralized identifier)
    3. **Issue a credential** — create a `NutsOrganizationCredential`
    4. **Load into wallet** — make the credential available for presentations
    5. **Discovery registration** — register at the pluginlake network discovery service
    6. **Search the network** — find other nodes via discovery

    ## Prerequisites

    Start the Nuts node sidecar:
    ```bash
    cd deploy/compose && docker compose -f docker-compose.nuts.yaml up -d
    ```

    The internal API is available at `http://127.0.0.1:8081`.
    """)


@app.cell
def _():
    import httpx

    NUTS_INTERNAL = "http://127.0.0.1:8081"
    NUTS_PUBLIC = "http://127.0.0.1:8080"
    return NUTS_INTERNAL, NUTS_PUBLIC, httpx


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 1. Health Check

    The Nuts node exposes a status endpoint on the internal API.
    If this fails, ensure the container is running.
    """)


@app.cell
def _(NUTS_INTERNAL, httpx, mo):
    _status = httpx.get(f"{NUTS_INTERNAL}/status")
    _diag = httpx.get(f"{NUTS_INTERNAL}/status/diagnostics")

    if _status.is_success:
        mo.output.replace(
            mo.md(f"""
✅ **Nuts node is healthy**

```yaml
{_diag.text}
```
""")
        )
    else:
        mo.output.replace(
            mo.md("❌ **Nuts node is not reachable.** Run `docker compose -f docker-compose.nuts.yaml up -d`")
        )


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 2. Create a Subject (DID)

    A "subject" in Nuts is a logical identity that owns a DID.
    Each pluginlake instance (hub or station) creates one subject.

    The Nuts node generates a `did:web` identifier based on its configured URL.

    **API:** `POST /internal/vdr/v2/subject`
    """)


@app.cell
def _(NUTS_INTERNAL, httpx, mo):
    _resp = httpx.post(f"{NUTS_INTERNAL}/internal/vdr/v2/subject", json={})
    _data = _resp.json()

    subject_id = _data["subject"]
    did = _data["documents"][0]["id"]

    mo.output.replace(
        mo.md(f"""
✅ **Subject created**

| Field | Value |
|-------|-------|
| Subject ID | `{subject_id}` |
| DID | `{did}` |

The subject ID is used in subsequent API calls to reference this identity.
The DID is the public identifier that other nodes will see.
""")
    )
    return did, subject_id


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 3. Issue a NutsOrganizationCredential

    This credential ties the DID to a real-world organization.
    In production, a trusted issuer (e.g., the network operator) issues this.
    In development, the node self-issues for testing.

    The credential contains:
    - `organization.name` — the legal organization name
    - `organization.city` — the city of the organization

    **API:** `POST /internal/vcr/v2/issuer/vc`
    """)


@app.cell
def _(NUTS_INTERNAL, did, httpx, mo):
    _vc_request = {
        "issuer": did,
        "type": "NutsOrganizationCredential",
        "credentialSubject": {
            "id": did,
            "organization": {
                "name": "Demo Ziekenhuis",
                "city": "Utrecht",
            },
        },
        "withStatusList2021Revocation": False,
        "expirationDate": "2027-01-01T00:00:00Z",
    }

    _resp = httpx.post(
        f"{NUTS_INTERNAL}/internal/vcr/v2/issuer/vc",
        json=_vc_request,
    )
    credential = _resp.json()

    mo.output.replace(
        mo.md(f"""
✅ **NutsOrganizationCredential issued**

| Field | Value |
|-------|-------|
| Credential ID | `{credential.get("id", "n/a")}` |
| Issuer | `{credential.get("issuer", "n/a")}` |
| Organization | {credential.get("credentialSubject", {}).get("organization", {}).get("name", "n/a")} |
| City | {credential.get("credentialSubject", {}).get("organization", {}).get("city", "n/a")} |
| Expires | `{credential.get("expirationDate", "n/a")}` |
| Proof type | `{credential.get("proof", {}).get("type", "n/a")}` |

The credential is now stored in the node's VCR (Verifiable Credential Registry)
but not yet in the subject's **wallet**.
""")
    )
    return (credential,)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 4. Load Credential into Wallet

    The wallet holds credentials that the subject can present to others.
    Issuing a credential stores it in the registry; loading it into the wallet
    makes it available for creating Verifiable Presentations (VPs).

    **API:** `POST /internal/vcr/v2/holder/{subject}/vc`
    """)


@app.cell
def _(NUTS_INTERNAL, credential, httpx, mo, subject_id):
    _resp = httpx.post(
        f"{NUTS_INTERNAL}/internal/vcr/v2/holder/{subject_id}/vc",
        json=credential,
    )

    if _resp.status_code == httpx.codes.NO_CONTENT:
        mo.output.replace(
            mo.md("""
✅ **Credential loaded into wallet**

The subject can now present this credential when registering at the
discovery service or when authenticating to other nodes.
""")
        )
    else:
        mo.output.replace(mo.md(f"❌ **Failed to load credential:** {_resp.status_code} — {_resp.text}"))


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 5. Verify Wallet Contents

    Let's confirm the credential is in the wallet.

    **API:** `GET /internal/vcr/v2/holder/{subject}/vc`
    """)


@app.cell
def _(NUTS_INTERNAL, httpx, mo, subject_id):
    _resp = httpx.get(f"{NUTS_INTERNAL}/internal/vcr/v2/holder/{subject_id}/vc")
    _wallet = _resp.json()

    mo.output.replace(
        mo.md(f"""
**Wallet contains {len(_wallet)} credential(s)**

Types: {", ".join(t for vc in _wallet for t in vc.get("type", []) if t != "VerifiableCredential")}
""")
    )


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 6. Discovery Service Registration

    The discovery service lets nodes find each other in the pluginlake network.
    Registration presents a Verifiable Presentation containing the
    `NutsOrganizationCredential` to the discovery server.

    The discovery server (in dev, hosted by the hub's Nuts node) validates the VP
    and adds the node to the network directory.

    **API:** `POST /internal/discovery/v1/{service_id}/{subject_id}`

    > ⚠️ This step requires the Nuts node to be configured as a discovery server
    > (`discovery.server.ids` in `nuts.yaml`). In the single-node dev setup,
    > the node acts as both server and client.
    """)


@app.cell
def _(NUTS_INTERNAL, httpx, mo, subject_id):
    _service_id = "pluginlake-network"
    _resp = httpx.post(
        f"{NUTS_INTERNAL}/internal/discovery/v1/{_service_id}/{subject_id}",
        json={},
    )

    if _resp.status_code in (200, 201, 204):
        mo.output.replace(
            mo.md(f"""
✅ **Registered at discovery service `{_service_id}`**

Other nodes querying the discovery service will now find this node.
The registration is automatically refreshed by the Nuts node.
""")
        )
    else:
        _error = _resp.json() if _resp.headers.get("content-type", "").startswith("application/") else _resp.text
        mo.output.replace(
            mo.md(f"""
⚠️ **Discovery registration returned {_resp.status_code}**

```json
{_error}
```

This is expected if the single-node compose doesn't have the discovery server enabled.
For the full network test, use the two-node compose in `tests/integration/nuts-network/`.
""")
        )


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 7. Search the Discovery Service

    Query the discovery service to find registered nodes.

    **API:** `GET /internal/discovery/v1/{service_id}?credentialSubject.organization.name=*`
    """)


@app.cell
def _(NUTS_INTERNAL, httpx, mo):
    _service_id = "pluginlake-network"
    _resp = httpx.get(
        f"{NUTS_INTERNAL}/internal/discovery/v1/{_service_id}/",
        params={"credentialSubject.organization.city": "*"},
    )

    if _resp.is_success:
        _results = _resp.json()
        if _results:
            _rows = ""
            for entry in _results:
                _cred = entry.get("credentialSubject", {})
                _org = _cred.get("organization", {})
                _rows += f"| {_org.get('name', '?')} | {_org.get('city', '?')} | `{entry.get('id', '?')[:50]}...` |\n"

            mo.output.replace(
                mo.md(f"""
✅ **Found {len(_results)} node(s) in the network**

| Organization | City | Credential ID |
|-------------|------|---------------|
{_rows}
""")
            )
        else:
            mo.output.replace(mo.md("No nodes registered yet (empty discovery service)."))
    else:
        mo.output.replace(mo.md(f"⚠️ Discovery search returned {_resp.status_code}: {_resp.text}"))


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 8. Request an Access Token (Node-to-Node Auth)

    When a hub wants to call a station, it requests a DPoP-bound access token
    from its local Nuts node. The Nuts node creates a Verifiable Presentation
    and exchanges it for a token at the target node's authorization server.

    **API:** `POST /internal/auth/v2/{subject}/request-service-access-token`

    ```json
    {
        "verifier": "did:web:target-node:8080:iam:...",
        "scope": "pluginlake-data-access"
    }
    ```

    > This step requires a second node to be running (the target).
    > See the two-node integration test for a complete example.
    """)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## 9. Validate Incoming Tokens (DPoP)

    When a station receives a request from a hub, it validates the DPoP token
    via its local Nuts node. This extracts the requester's identity.

    **API:** `POST /internal/auth/v2/dpop/validate`

    ```json
    {
        "token": "<access_token>",
        "dpop": "<dpop_proof_header>"
    }
    ```

    The response contains the introspection result with:
    - `iss` — the DID of the requesting organization
    - `scope` — the granted scope
    - `active` — whether the token is valid

    > This is what the FastAPI middleware will call in the next story.
    """)


@app.cell
def _(mo):
    mo.md(r"""
    ---
    ## Summary

    The full flow for a pluginlake node joining the network:

    ```
    ┌─────────────────────────────────────────────────────┐
    │ 1. Create subject (DID)                             │
    │    POST /internal/vdr/v2/subject                    │
    ├─────────────────────────────────────────────────────┤
    │ 2. Issue NutsOrganizationCredential                 │
    │    POST /internal/vcr/v2/issuer/vc                  │
    ├─────────────────────────────────────────────────────┤
    │ 3. Load credential into wallet                      │
    │    POST /internal/vcr/v2/holder/{subject}/vc        │
    ├─────────────────────────────────────────────────────┤
    │ 4. Register at discovery service                    │
    │    POST /internal/discovery/v1/{service}/{subject}  │
    ├─────────────────────────────────────────────────────┤
    │ 5. Request access tokens for cross-node calls       │
    │    POST /internal/auth/v2/{sub}/request-service-... │
    ├─────────────────────────────────────────────────────┤
    │ 6. Validate incoming tokens                         │
    │    POST /internal/auth/v2/dpop/validate             │
    └─────────────────────────────────────────────────────┘
    ```

    Next steps:
    - **Two-node network test** — see `tests/integration/nuts-network/`
    - **FastAPI middleware** — validates DPoP tokens on incoming requests
    - **Bootstrap automation** — scripts to set up DIDs and credentials on startup
    """)


@app.cell
def _():
    import marimo as mo

    return (mo,)


if __name__ == "__main__":
    app.run()
