"""Upload Synthea test data (OMOP CSVs and FHIR NDJSON) to the pluginlake API.

Downloads the data from GitHub releases if not already present, then uploads
each file to the corresponding API endpoint.

Usage:
    uv run python scripts/upload_synthea.py              # upload both OMOP and FHIR
    uv run python scripts/upload_synthea.py --omop        # upload OMOP only
    uv run python scripts/upload_synthea.py --fhir        # upload FHIR only
    uv run python scripts/upload_synthea.py --api-url http://host:8000  # custom API URL
"""

import argparse
import re
import sys
from pathlib import Path

import httpx

from pluginlake.utils.testdata import ensure_synthea1k, ensure_synthea_fhir_ndjson, find_repo_root

API_URL = "http://localhost:8000"
TIMEOUT = httpx.Timeout(timeout=120.0)


def _pascal_to_snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def upload_omop(api_url: str, data_dir: Path) -> bool:
    ok = True
    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {data_dir}")
        return False

    print(f"\n--- Uploading {len(csv_files)} OMOP tables ---")
    for csv_file in csv_files:
        table_name = csv_file.stem
        size_mb = csv_file.stat().st_size / (1024 * 1024)
        print(f"  {table_name} ({size_mb:.1f} MB) ...", end=" ", flush=True)

        with csv_file.open("rb") as fp:
            r = httpx.post(
                f"{api_url}/api/v1/omop/{table_name}/csv",
                files={"file": (csv_file.name, fp, "text/csv")},
                timeout=TIMEOUT,
            )

        if r.status_code == 201:
            data = r.json()
            run_id = data.get("dagster_run_id", "n/a")
            print(f"OK (run={run_id})")
        else:
            print(f"FAILED ({r.status_code}: {r.text})")
            ok = False

    return ok


def upload_fhir(api_url: str, data_dir: Path) -> bool:
    ok = True
    ndjson_files = sorted(data_dir.glob("*.ndjson"))
    if not ndjson_files:
        print(f"No NDJSON files found in {data_dir}")
        return False

    from pluginlake.fhir.translator_registry import FHIR_RESOURCE_TYPES

    supported = set(FHIR_RESOURCE_TYPES)
    mapped = []
    skipped = []
    for f in ndjson_files:
        api_name = _pascal_to_snake(f.stem)
        if api_name in supported:
            mapped.append((f, api_name))
        else:
            skipped.append(f.stem)

    if skipped:
        print(f"\n  Skipping unsupported resource types: {', '.join(skipped)}")

    print(f"\n--- Uploading {len(mapped)} FHIR resources ---")
    for ndjson_file, resource_type in mapped:
        size_mb = ndjson_file.stat().st_size / (1024 * 1024)
        print(f"  {resource_type} ({size_mb:.1f} MB) ...", end=" ", flush=True)

        with ndjson_file.open("rb") as fp:
            r = httpx.post(
                f"{api_url}/api/v1/fhir/{resource_type}/ndjson",
                files={"file": (ndjson_file.name, fp, "application/x-ndjson")},
                timeout=TIMEOUT,
            )

        if r.status_code == 201:
            data = r.json()
            run_id = data.get("dagster_run_id", "n/a")
            print(f"OK (run={run_id})")
        else:
            print(f"FAILED ({r.status_code}: {r.text})")
            ok = False

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload Synthea test data to the pluginlake API")
    parser.add_argument("--api-url", default=API_URL, help=f"API base URL (default: {API_URL})")
    parser.add_argument("--omop", action="store_true", help="Upload OMOP data only")
    parser.add_argument("--fhir", action="store_true", help="Upload FHIR data only")
    args = parser.parse_args()

    upload_both = not args.omop and not args.fhir

    project_root = find_repo_root()
    ok = True

    if args.omop or upload_both:
        omop_dir = ensure_synthea1k(project_root=project_root)
        ok &= upload_omop(args.api_url, omop_dir)

    if args.fhir or upload_both:
        fhir_dir = ensure_synthea_fhir_ndjson(project_root=project_root)
        ok &= upload_fhir(args.api_url, fhir_dir)

    if ok:
        print("\nAll uploads completed successfully.")
        return 0
    else:
        print("\nSome uploads failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
