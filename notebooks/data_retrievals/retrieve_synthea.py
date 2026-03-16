"""Download Synthea Sample Data

Retrieve pre-generated synthetic patient data in FHIR and OMOP formats
from GitHub releases for local development and testing.
"""

import marimo

__generated_with = "0.20.2"
app = marimo.App()


@app.cell
def _():
    from pluginlake.utils.testdata import ensure_synthea1k, ensure_synthea_fhir_ndjson, find_repo_root

    PROJECT_ROOT = find_repo_root()
    FHIR_DIR = ensure_synthea_fhir_ndjson(project_root=PROJECT_ROOT)
    OMOP_DIR = ensure_synthea1k(project_root=PROJECT_ROOT)
    return FHIR_DIR, OMOP_DIR


@app.cell
def _(FHIR_DIR, OMOP_DIR):
    total_size = 0
    for data_dir in [FHIR_DIR, OMOP_DIR]:
        if not data_dir.exists():
            continue
        print(f"\n{data_dir.name}/")
        for path in sorted(data_dir.rglob("*")):
            if path.is_file():
                size_mb = path.stat().st_size / (1024 * 1024)
                total_size += path.stat().st_size
                rel_path = path.relative_to(data_dir)
                print(f"  {rel_path} ({size_mb:.1f} MB)")
    print(f"\nTotal: {total_size / (1024**3):.2f} GB")


if __name__ == "__main__":
    app.run()
