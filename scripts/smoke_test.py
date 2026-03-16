"""Smoke test for the full ingestion pipeline with vocabulary validation.

Runs against the Docker dev stack. Tests:
1. Trigger vocabulary materialization (fixture vocab files mounted in container)
2. Upload clinical person table with a known invalid concept ID (race_concept_id=999999)
3. Trigger clinical materialization
4. Verify validation metadata in Dagster (invalid_concept_count > 0)

Usage:
    just smoke-test-full     # start isolated stack, test, tear down
    just smoke-test          # run against already-running stack
    uv run python scripts/smoke_test.py  # same as smoke-test
"""

import sys
import time
from pathlib import Path

import httpx

DAGSTER_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
GRAPHQL_URL = f"{DAGSTER_URL}/graphql"

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "integration" / "fixtures"
CLINICAL_DIR = FIXTURES_DIR / "clinical"

POLL_INTERVAL = 2
POLL_TIMEOUT = 120

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

ASSET_MATERIALIZATION_QUERY = """
query AssetMaterialization($assetKey: AssetKeyInput!) {
  assetOrError(assetKey: $assetKey) {
    __typename
    ... on Asset {
      assetMaterializations(limit: 1) {
        runId
        metadataEntries {
          __typename
          label
          ... on IntMetadataEntry { intValue }
          ... on JsonMetadataEntry { jsonString }
          ... on TextMetadataEntry { text }
        }
      }
    }
  }
}
"""

LAUNCH_JOB_MUTATION = """
mutation LaunchRun($executionParams: ExecutionParams!) {
  launchRun(executionParams: $executionParams) {
    __typename
    ... on LaunchRunSuccess { run { runId status } }
    ... on PythonError { message }
    ... on RunConfigValidationInvalid { errors { message } }
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


def _launch_job(job_name: str, asset_selection: list[list[str]] | None = None) -> str:
    params: dict = {
        "selector": {
            "repositoryLocationName": "pluginlake.definitions",
            "repositoryName": "__repository__",
            "jobName": job_name,
        },
        "runConfigData": {},
    }
    if asset_selection:
        params["selector"]["assetSelection"] = [{"path": p} for p in asset_selection]

    result = _graphql(LAUNCH_JOB_MUTATION, {"executionParams": params})
    launch = result["data"]["launchRun"]

    if launch["__typename"] != "LaunchRunSuccess":
        raise SmokeTestError(f"Failed to launch {job_name}: {launch}")

    run_id = launch["run"]["runId"]
    print(f"  Launched: {run_id}")
    return run_id


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


def step_vocab() -> None:
    print("\n--- Step 1: Materialize vocabulary tables ---")
    run_id = _launch_job("omop_vocab_ingest_job")
    status = wait_for_run(run_id, "vocab")
    if status != "SUCCESS":
        raise SmokeTestError(f"Vocab job ended with: {status}")


def step_clinical() -> None:
    print("\n--- Step 2: Upload and materialize clinical data ---")
    person_csv = CLINICAL_DIR / "person.csv"
    if not person_csv.exists():
        raise SmokeTestError(f"Fixture not found: {person_csv}")

    with person_csv.open("rb") as fp:
        r = httpx.post(
            f"{API_URL}/api/v1/omop/person/csv",
            files={"file": (person_csv.name, fp, "text/csv")},
            timeout=30,
        )
    if r.status_code != 201:
        raise SmokeTestError(f"Upload failed: {r.status_code} {r.text}")

    data = r.json()
    run_id = data.get("dagster_run_id")
    print(f"  Uploaded person.csv (run_id={run_id})")

    if run_id:
        status = wait_for_run(run_id, "clinical")
        if status != "SUCCESS":
            raise SmokeTestError(f"Clinical job ended with: {status}")
    else:
        print("  No run_id returned, triggering manually...")
        run_id = _launch_job("omop_ingest_job", [["omop", "person"]])
        status = wait_for_run(run_id, "clinical")
        if status != "SUCCESS":
            raise SmokeTestError(f"Clinical job ended with: {status}")


def step_verify() -> None:
    print("\n--- Step 3: Verify validation metadata ---")
    data = _graphql(
        ASSET_MATERIALIZATION_QUERY,
        {"assetKey": {"path": ["omop", "person"]}},
    )
    asset = data["data"]["assetOrError"]
    if asset["__typename"] != "Asset":
        raise SmokeTestError(f"Asset query error: {asset}")

    mats = asset.get("assetMaterializations", [])
    if not mats:
        raise SmokeTestError("No materializations found for omop/person")

    entries = {e["label"]: e for e in mats[0].get("metadataEntries", [])}
    print(f"  Metadata keys: {sorted(entries.keys())}")

    passed = True

    if "row_count" in entries:
        row_count = entries["row_count"].get("intValue")
        print(f"  row_count = {row_count}")
        if row_count != 5:
            print(f"  WARN: Expected 5 rows, got {row_count}")
    else:
        print("  FAIL: row_count missing")
        passed = False

    if "invalid_concept_count" in entries:
        count = entries["invalid_concept_count"].get("intValue")
        print(f"  invalid_concept_count = {count}")
        if count is not None and count > 0:
            print("  PASS: Vocabulary validation detected invalid concepts")
        else:
            print("  FAIL: Expected invalid concepts (race_concept_id=999999) but count=0")
            passed = False
    else:
        print("  FAIL: invalid_concept_count missing — validation did not run")
        passed = False

    if "invalid_concepts" in entries:
        detail = entries["invalid_concepts"].get("jsonString") or entries["invalid_concepts"].get("text", "present")
        print(f"  invalid_concepts = {detail}")
        print("  PASS: Invalid concept summary attached")
    else:
        if entries.get("invalid_concept_count", {}).get("intValue", 0) > 0:
            print("  FAIL: invalid_concepts summary missing despite count > 0")
            passed = False

    if not passed:
        raise SmokeTestError("Validation metadata checks failed")


def main() -> int:
    print("=" * 60)
    print("PLUGINLAKE SMOKE TEST — Vocabulary Validation Pipeline")
    print("=" * 60)

    try:
        wait_for_services()
        step_vocab()
        step_clinical()
        step_verify()

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
