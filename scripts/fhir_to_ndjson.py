"""Convert Synthea FHIR Bundle JSON files to NDJSON grouped by resource type.

Reads all Bundle JSON files from data/synthea/fhir/, extracts each entry's
resource, and writes one NDJSON file per resource type into data/synthea/ndjson/.

Usage:
    uv run python scripts/fhir_to_ndjson.py
    uv run python scripts/fhir_to_ndjson.py --fhir-dir data/synthea/fhir/fhir --ndjson-dir data/synthea/ndjson
"""

import argparse
import json
import sys
from collections import defaultdict
from io import TextIOWrapper
from pathlib import Path


def convert_bundles(fhir_dir: Path, ndjson_dir: Path) -> None:
    ndjson_dir.mkdir(parents=True, exist_ok=True)

    bundle_files = sorted(fhir_dir.glob("*.json"))
    if not bundle_files:
        print(f"No JSON files found in {fhir_dir}", file=sys.stderr)
        sys.exit(1)

    total = len(bundle_files)
    print(f"Converting {total} FHIR Bundles → NDJSON in {ndjson_dir}")

    counts: dict[str, int] = defaultdict(int)
    handles: dict[str, TextIOWrapper] = {}

    try:
        for i, path in enumerate(bundle_files, 1):
            with path.open() as f:
                bundle = json.load(f)

            for entry in bundle.get("entry", []):
                resource = entry.get("resource")
                if resource is None:
                    continue
                rtype = resource.get("resourceType", "Unknown")
                if rtype not in handles:
                    handles[rtype] = (ndjson_dir / f"{rtype}.ndjson").open("w")
                handles[rtype].write(json.dumps(resource, separators=(",", ":")) + "\n")
                counts[rtype] += 1

            if i % 10_000 == 0 or i == total:
                print(f"  {i}/{total} files processed")
    finally:
        for fh in handles.values():
            fh.close()

    print("\nResource counts:")
    for rtype, count in sorted(counts.items()):
        print(f"  {rtype}: {count:,}")
    print(f"\nTotal resources: {sum(counts.values()):,}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert FHIR Bundles to NDJSON by resource type")
    parser.add_argument(
        "--fhir-dir",
        type=Path,
        default=Path("data/synthea/fhir/fhir"),
        help="Directory containing FHIR Bundle JSON files",
    )
    parser.add_argument(
        "--ndjson-dir",
        type=Path,
        default=Path("data/synthea/ndjson"),
        help="Output directory for NDJSON files",
    )
    args = parser.parse_args()

    if not args.fhir_dir.is_dir():
        print(f"FHIR directory not found: {args.fhir_dir}", file=sys.stderr)
        return 1

    convert_bundles(args.fhir_dir, args.ndjson_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
