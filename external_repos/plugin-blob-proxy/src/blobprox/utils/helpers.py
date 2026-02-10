import json
import os


def read_json(path: str) -> dict:
    """Read and return the contents of a JSON file."""

    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r") as file:
        return json.load(file)


def string_to_bool(value: str) -> bool:
    """Convert a string to a boolean."""
    return value.lower() in ("true", "1", "t")
