import marimo

__generated_with = "0.13.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import subprocess

    import marimo as mo

    return json, mo, subprocess


@app.cell
def _(mo):
    mo.md(
        """
        # Azure RBAC Manager

        Manage service principal access to pluginlake's Container Registry and Blob Storage.

        **Prerequisite:** Run `az login` before using this notebook.
        """
    )


@app.cell
def _():
    # --- Configuration ---
    # Change these to match your environment.
    RESOURCE_GROUP = "rg-plugin-demo-d"
    ACR_NAME = "crplugindemod"
    STORAGE_ACCOUNT = "stplugindemod"

    # Set this to the Object ID of the service principal you want to manage.
    # Find it with: az ad sp show --id <APP_ID> --query id -o tsv
    SERVICE_PRINCIPAL_OID = ""
    return ACR_NAME, RESOURCE_GROUP, SERVICE_PRINCIPAL_OID, STORAGE_ACCOUNT


@app.cell
def _(json, subprocess):
    def az(args: list[str]) -> dict | list | str:
        """Run an az CLI command and return parsed JSON or raw text."""
        result = subprocess.run(
            ["az", *args, "-o", "json"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        text = result.stdout.strip()
        if not text:
            return {}
        return json.loads(text)

    def get_acr_id(acr_name: str) -> str:
        """Get the full resource ID of an ACR."""
        data = az(["acr", "show", "--name", acr_name, "--query", "id"])
        return data.strip('"') if isinstance(data, str) else str(data)

    def get_storage_id(account_name: str) -> str:
        """Get the full resource ID of a storage account."""
        data = az(
            [
                "storage",
                "account",
                "show",
                "--name",
                account_name,
                "--query",
                "id",
            ]
        )
        return data.strip('"') if isinstance(data, str) else str(data)

    def list_containers(account_name: str) -> list[str]:
        """List all blob container names in a storage account."""
        items = az(
            [
                "storage",
                "container",
                "list",
                "--account-name",
                account_name,
                "--auth-mode",
                "login",
                "--query",
                "[].name",
            ]
        )
        return items if isinstance(items, list) else []

    def list_roles(scope: str, assignee: str) -> list[dict]:
        """List role assignments for an assignee at a given scope."""
        return az(
            [
                "role",
                "assignment",
                "list",
                "--scope",
                scope,
                "--assignee",
                assignee,
            ]
        )

    def grant_role(scope: str, role: str, assignee: str) -> dict:
        """Assign a role to a service principal."""
        result = az(
            [
                "role",
                "assignment",
                "create",
                "--scope",
                scope,
                "--role",
                role,
                "--assignee-object-id",
                assignee,
                "--assignee-principal-type",
                "ServicePrincipal",
            ]
        )
        print(f"Granted '{role}' to {assignee}")
        return result

    def revoke_role(scope: str, role: str, assignee: str) -> None:
        """Remove a role from a service principal."""
        subprocess.run(
            [
                "az",
                "role",
                "assignment",
                "delete",
                "--scope",
                scope,
                "--role",
                role,
                "--assignee",
                assignee,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Revoked '{role}' from {assignee}")

    return az, get_acr_id, get_storage_id, grant_role, list_containers, list_roles, revoke_role


@app.cell
def _(mo):
    mo.md(
        """
        ---
        ## Container Registry

        Use `acr_grant()` and `acr_revoke()` with one of these presets:

        | Preset | Roles granted |
        |---|---|
        | `"pull"` | AcrPull |
        | `"push"` | AcrPush |
        | `"push+pull"` | AcrPush + AcrPull |
        """
    )


@app.cell
def _(ACR_NAME, SERVICE_PRINCIPAL_OID, get_acr_id, grant_role, list_roles, revoke_role):
    ACR_PRESETS = {
        "pull": ["AcrPull"],
        "push": ["AcrPush"],
        "push+pull": ["AcrPush", "AcrPull"],
    }

    def acr_list():
        """List current ACR role assignments for the service principal."""
        acr_id = get_acr_id(ACR_NAME)
        assignments = list_roles(acr_id, SERVICE_PRINCIPAL_OID)
        if not assignments:
            print("No role assignments found.")
            return
        for a in assignments:
            print(f"  {a.get('roleDefinitionName', '?')}")

    def acr_grant(preset: str = "pull"):
        """Grant ACR access. preset: 'pull', 'push', or 'push+pull'."""
        acr_id = get_acr_id(ACR_NAME)
        for role in ACR_PRESETS[preset]:
            grant_role(acr_id, role, SERVICE_PRINCIPAL_OID)

    def acr_revoke(preset: str = "pull"):
        """Revoke ACR access. preset: 'pull', 'push', or 'push+pull'."""
        acr_id = get_acr_id(ACR_NAME)
        for role in ACR_PRESETS[preset]:
            revoke_role(acr_id, role, SERVICE_PRINCIPAL_OID)

    return acr_grant, acr_list, acr_revoke


@app.cell
def _(mo):
    mo.md(
        """
        ---
        ## Blob Storage

        Use `blob_grant()` and `blob_revoke()` with one of these presets:

        | Preset | Roles granted |
        |---|---|
        | `"read"` | Storage Blob Data Reader |
        | `"read+write"` | Storage Blob Data Contributor |
        | `"read+write+delete"` | Storage Blob Data Contributor + Storage Blob Data Owner |

        Pass `container="mycontainer"` to scope to a specific container, or omit it to apply to the entire account.
        """
    )


@app.cell
def _(SERVICE_PRINCIPAL_OID, STORAGE_ACCOUNT, get_storage_id, grant_role, list_roles, revoke_role):
    BLOB_PRESETS = {
        "read": ["Storage Blob Data Reader"],
        "read+write": ["Storage Blob Data Contributor"],
        "read+write+delete": ["Storage Blob Data Contributor", "Storage Blob Data Owner"],
    }

    def _blob_scope(container: str | None = None) -> str:
        storage_id = get_storage_id(STORAGE_ACCOUNT)
        if container:
            return f"{storage_id}/blobServices/default/containers/{container}"
        return storage_id

    def blob_list(container: str | None = None):
        """List current blob role assignments for the service principal."""
        scope = _blob_scope(container)
        assignments = list_roles(scope, SERVICE_PRINCIPAL_OID)
        if not assignments:
            print("No role assignments found at this scope.")
            return
        for a in assignments:
            print(f"  {a.get('roleDefinitionName', '?')}")

    def blob_grant(preset: str = "read", container: str | None = None):
        """Grant blob access. preset: 'read', 'read+write', or 'read+write+delete'."""
        scope = _blob_scope(container)
        for role in BLOB_PRESETS[preset]:
            grant_role(scope, role, SERVICE_PRINCIPAL_OID)

    def blob_revoke(preset: str = "read", container: str | None = None):
        """Revoke blob access. preset: 'read', 'read+write', or 'read+write+delete'."""
        scope = _blob_scope(container)
        for role in BLOB_PRESETS[preset]:
            revoke_role(scope, role, SERVICE_PRINCIPAL_OID)

    return blob_grant, blob_list, blob_revoke


@app.cell
def _(mo):
    mo.md(
        """
        ---
        ## Usage Examples

        ```python
        # List current ACR roles
        acr_list()

        # Grant push+pull to ACR
        acr_grant("push+pull")

        # Revoke push (keep pull)
        acr_revoke("push")

        # Grant read-only to entire storage account
        blob_grant("read")

        # Grant read+write to a specific container
        blob_grant("read+write", container="raw")

        # List roles on a container
        blob_list(container="raw")

        # Revoke all blob access
        blob_revoke("read+write+delete")
        ```
        """
    )


@app.cell
def _(mo):
    mo.md(
        """
        ---
        ## Quick Reference

        ```bash
        # Find a service principal's Object ID
        az ad sp show --id <APP_ID> --query id -o tsv

        # Create a new service principal (no role assignment)
        az ad sp create-for-rbac --name "sp-pluginlake-<purpose>" --skip-assignment

        # List all SPs with pluginlake in the name
        az ad sp list --display-name "sp-pluginlake" \\
            --query "[].{name:displayName, appId:appId, objectId:id}" -o table
        ```
        """
    )


if __name__ == "__main__":
    app.run()
