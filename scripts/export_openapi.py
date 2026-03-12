"""Export the FastAPI OpenAPI schema to a static JSON file.

Usage:
    uv run python scripts/export_openapi.py
    uv run python scripts/export_openapi.py --output docs/openapi.json
"""

import argparse
import json
from pathlib import Path

from pluginlake.api.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the pluginlake OpenAPI schema.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/openapi.json"),
        help="Output path for the JSON file (default: docs/openapi.json)",
    )
    args = parser.parse_args()

    app = create_app()
    schema = app.openapi()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"OpenAPI schema written to {args.output}")  # noqa: T201


if __name__ == "__main__":
    main()
