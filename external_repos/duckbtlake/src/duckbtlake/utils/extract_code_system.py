import json
from pathlib import Path

import polars as pl

SCHEMAS_ROOT = Path("schemas")


def extract_code_system_schema(csv_path: Path, code_column: str, out_path: Path) -> dict:
    """
    Read a CSV, collect unique codes, and return a JSON-Schema dict
    whose $id is the path within the schemas directory (e.g. 'refs/agb_codes.json').
    """
    df = pl.read_csv(str(csv_path), separator=";", schema_overrides={code_column: pl.Utf8})
    codes = df[code_column].unique().to_list()
    schema_id = str(out_path.relative_to(SCHEMAS_ROOT))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        "type": "string",
        "enum": codes,
    }


def write_schema_file(schema: dict, out_path: Path) -> None:
    """Serialize the schema dict to a pretty-printed JSON file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(schema, indent=2))


def generate_schemas(tasks: list[tuple[Path, str, Path]]) -> None:
    """
    Given tasks = [(csv_path, code_column, output_schema_path), ...],
    generate each JSON‐Schema file.
    """
    for csv_path, code_column, out_path in tasks:
        schema = extract_code_system_schema(csv_path, code_column, out_path)
        write_schema_file(schema, out_path)
        print(f"Wrote {len(schema['enum'])} codes → {out_path}")


if __name__ == "__main__":
    tasks = [
        (Path("data/references/Zorginstellingen.csv"), "ZhCode", Path("schemas/refs/agb_codes.json")),
        (
            Path("data/references/20230517_Dbc_Specialisme.csv"),
            "SpecialismeCode",
            Path("schemas/refs/specialty_codes.json"),
        ),
        (
            Path("data/references/20230517_Dbc_Icd10Diagnose_Tijdsafhankelijk.csv"),
            "Icd10DiagnoseCodeMetDaggerAsterisk",
            Path("schemas/refs/icd10_codes.json"),
        ),
        (
            Path("data/references/20230517_Dbc_Zorgactiviteit_Tijdsafhankelijk.csv"),
            "ZorgactiviteitCode",
            Path("schemas/refs/za_codes.json"),
        ),
    ]
    generate_schemas(tasks)
