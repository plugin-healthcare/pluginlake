from pathlib import Path


def validate_path(path: str) -> Path:
    """Validate the path and return a Path object"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Path {path} does not exist")
    return path
