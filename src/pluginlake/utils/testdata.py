"""Synthea test/demo data retrieval for notebooks and development.

For OMOP vocabulary provisioning (production), use
:func:`pluginlake.omop.provisioning.ensure_omop_vocabularies` instead.
"""

from pathlib import Path

from pluginlake.utils.download import download_and_extract
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_SYNTHEA1K_URL = (
    "https://github.com/plugin-healthcare/pluginlake-testdata/releases/download/synthea1k-v1/synthea1k.tar.gz"
)
_SYNTHEA_FHIR_NDJSON_URL = "https://github.com/plugin-healthcare/pluginlake-testdata/releases/download/synthea-fhir-ndjson-v1/synthea_fhir_ndjson.tar.gz"
_SYNTHEA1K_DEST = Path("data/synthea/omop/synthea1k")
_SYNTHEA_FHIR_NDJSON_DEST = Path("data/synthea/fhir/ndjson")


def find_repo_root() -> Path:
    """Walk up from this file to find the directory containing pyproject.toml."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    msg = "Could not find repo root (no pyproject.toml found)"
    raise FileNotFoundError(msg)


def ensure_synthea1k(project_root: Path | None = None) -> Path:
    """Ensure Synthea 1K test data is available locally."""
    root = project_root or find_repo_root()
    return download_and_extract(_SYNTHEA1K_URL, root / _SYNTHEA1K_DEST)


def ensure_synthea_fhir_ndjson(project_root: Path | None = None) -> Path:
    """Ensure Synthea FHIR NDJSON files are available locally."""
    root = project_root or find_repo_root()
    return download_and_extract(_SYNTHEA_FHIR_NDJSON_URL, root / _SYNTHEA_FHIR_NDJSON_DEST)
