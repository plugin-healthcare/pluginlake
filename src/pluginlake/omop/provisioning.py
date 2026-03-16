"""OMOP vocabulary provisioning.

Downloads and extracts OMOP vocabulary files required for concept
validation and FHIR-to-OMOP translation.
"""

from pathlib import Path

from pluginlake.omop.config import get_omop_settings
from pluginlake.utils.download import download_and_extract
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


def ensure_omop_vocabularies(dest_dir: Path | None = None) -> Path:
    """Ensure OMOP vocabulary files are available locally.

    Downloads and extracts the vocabulary archive when the target
    directory is empty or missing.  Skips if files already exist.

    Args:
        dest_dir: Override for the vocabulary directory.  Falls back
            to ``OMOPSettings.vocabulary_dir`` when *None*.

    Returns:
        Path to the vocabulary directory.
    """
    settings = get_omop_settings()
    target = dest_dir or settings.vocabulary_dir
    return download_and_extract(settings.vocabulary_url, target)
