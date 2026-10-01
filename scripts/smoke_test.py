"""Smoke test for the pluginlake core stack.

Runs against the Docker dev stack and verifies core, project-agnostic
behaviour only. Project pipelines such as the EHDS/OMOP assets live in their
own repositories (ADR-009) and are tested there.

Checks:
1. API and Dagster webserver come up and answer health probes
2. Core API routers respond (health, ingest info, catalog, assets)
3. Every Dagster code location loads without errors
4. A generic file upload through ``POST /api/v1/ingest`` is stored

Usage:
    just smoke-test-full     # start isolated stack, test, tear down
    just smoke-test          # run against already-running stack
    uv run python scripts/smoke_test.py  # same as smoke-test
"""

import sys
import tempfile
import time
from pathlib import Path

import httpx

DAGSTER_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
GRAPHQL_URL = f"{DAGSTER_URL}/graphql"

POLL_INTERVAL = 2
POLL_TIMEOUT = 120

SMOKE_DATASET = "smoke"

RUN_STATUS_QUERY = """
query RunStatus($runId: ID!) {
  runOrError(runId: $runId) {
    __typename
    ... on Run { runId status }
    ... on RunNotFoundError { message }
    ... on PythonError { message }
  }
}
"""

WORKSPACE_QUERY = """
query Workspace {
  workspaceOrError {
    __typename
    ... on Workspace {
      locationEntries {
        name
        loadStatus
        locationOrLoadError {
          __typename
          ... on RepositoryLocation {
            name
            repositories {
              name
              jobs { name }
              assetNodes { assetKey { path } }
            }
          }
          ... on PythonError { message }
        }
      }
    }
    ... on PythonError { message }
  }
}
"""


class SmokeTestError(Exception):
    pass


def _graphql(query: str, variables: dict | None = None) -> dict:
    r = httpx.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _get(path: str) -> httpx.Response:
    return httpx.get(f"{API_URL}{path}", timeout=30)


def wait_for_services() -> None:
    print("Waiting for services...")
    deadline = time.time() + 90
    checks = {"API": f"{API_URL}/health", "Dagster": f"{DAGSTER_URL}/server_info"}
    pending = set(checks.keys())

    while pending and time.time() < deadline:
        for name in list(pending):
            try:
                if httpx.get(checks[name], timeout=3).status_code == 200:
                    print(f"  {name}: ready")
                    pending.discard(name)
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError):
                pass
        if pending:
            time.sleep(2)

    if pending:
        raise SmokeTestError(f"Services not ready after 90s: {pending}")


def wait_for_run(run_id: str, label: str = "run") -> str:
    print(f"  Polling {label}...", end="", flush=True)
    deadline = time.time() + POLL_TIMEOUT

    while time.time() < deadline:
        data = _graphql(RUN_STATUS_QUERY, {"runId": run_id})
        run = data["data"]["runOrError"]

        if run["__typename"] != "Run":
            raise SmokeTestError(f"Run query error: {run}")

        status = run["status"]
        if status in {"SUCCESS", "FAILURE", "CANCELED"}:
            print(f" {status}")
            return status

        print(".", end="", flush=True)
        time.sleep(POLL_INTERVAL)

    raise SmokeTestError(f"Run {run_id} timed out after {POLL_TIMEOUT}s")


def step_api() -> None:
    print("\n--- Step 1: Core API endpoints ---")
    for path in ("/health", "/ready", "/api/v1/ingest/info", "/api/v1/catalog/schemas", "/api/v1/assets"):
        r = _get(path)
        if r.status_code != 200:
            raise SmokeTestError(f"GET {path} returned {r.status_code}: {r.text}")
        print(f"  {path}: 200")

    info = _get("/api/v1/ingest/info").json()
    if not info.get("allowed_extensions"):
        raise SmokeTestError(f"Ingest info missing allowed_extensions: {info}")
    print(f"  allowed_extensions = {info['allowed_extensions']}")


def step_dagster_workspace() -> None:
    print("\n--- Step 2: Dagster code locations ---")
    workspace = _graphql(WORKSPACE_QUERY)["data"]["workspaceOrError"]
    if workspace["__typename"] != "Workspace":
        raise SmokeTestError(f"Workspace query error: {workspace}")

    entries = workspace["locationEntries"]
    if not entries:
        raise SmokeTestError("Dagster reports no code locations")

    for entry in entries:
        location = entry["locationOrLoadError"]
        if location["__typename"] != "RepositoryLocation":
            raise SmokeTestError(f"Code location '{entry['name']}' failed to load: {location}")

        repos = location["repositories"]
        jobs = [job["name"] for repo in repos for job in repo["jobs"]]
        assets = ["/".join(node["assetKey"]["path"]) for repo in repos for node in repo["assetNodes"]]
        print(f"  {entry['name']}: {entry['loadStatus']}, {len(jobs)} job(s), {len(assets)} asset(s)")
        if assets:
            print(f"    assets: {sorted(assets)[:10]}")

    print("  PASS: all code locations loaded without errors")


def step_ingest() -> None:
    print("\n--- Step 3: Generic file ingestion ---")
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "smoke.csv"
        csv_path.write_text("id,value\n1,alpha\n2,beta\n")

        with csv_path.open("rb") as fp:
            r = httpx.post(
                f"{API_URL}/api/v1/ingest",
                files={"file": (csv_path.name, fp, "text/csv")},
                data={"dataset": SMOKE_DATASET},
                timeout=30,
            )

    if r.status_code != 201:
        raise SmokeTestError(f"Upload failed: {r.status_code} {r.text}")

    data = r.json()
    print(f"  Stored at {data['file_path']} ({data['size_bytes']} bytes, status={data['status']})")
    if data["size_bytes"] <= 0:
        raise SmokeTestError(f"Unexpected size_bytes: {data['size_bytes']}")

    run_id = data.get("dagster_run_id")
    if run_id:
        status = wait_for_run(run_id, "ingest")
        if status != "SUCCESS":
            raise SmokeTestError(f"Ingest run ended with: {status}")
    else:
        print("  No Dagster run triggered (no project pipeline installed)")


def main() -> int:
    print("=" * 60)
    print("PLUGINLAKE SMOKE TEST — Core Stack")
    print("=" * 60)

    try:
        wait_for_services()
        step_api()
        step_dagster_workspace()
        step_ingest()

        print("\n" + "=" * 60)
        print("SMOKE TEST PASSED")
        print("=" * 60)
        return 0

    except SmokeTestError as e:
        print(f"\nSMOKE TEST FAILED: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
