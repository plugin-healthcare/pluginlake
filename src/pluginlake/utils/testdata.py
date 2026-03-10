"""Automated test data retrieval for notebooks and development."""

import os
import shutil
import tarfile
import tempfile
from pathlib import Path

import httpx

from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)

_SYNTHEA1K_URL = (
    "https://github.com/plugin-healthcare/pluginlake-testdata/releases/download/synthea1k-v1/synthea1k.tar.gz"
)
_OMOP_VOCAB_URL = "https://github.com/plugin-healthcare/pluginlake-testdata/releases/download/omop-vocabularies-v1/omop_vocabularies.tar.gz"
_SYNTHEA1K_DEST = Path("data/synthea/omop/synthea1k")
_OMOP_VOCAB_DEST = Path("data/omop_vocabularies")


def _download_and_extract(url: str, dest_dir: Path) -> Path:
    if dest_dir.exists() and any(dest_dir.iterdir()):
        logger.warning("Data already exists at %s, skipping download", dest_dir)
        return dest_dir

    dest_dir.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".tar.gz", dir=dest_dir.parent)
    tmp_file = Path(tmp_path)
    try:
        logger.info("Downloading %s ...", url)
        with (
            httpx.Client(follow_redirects=True, timeout=httpx.Timeout(timeout=300.0)) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))

            try:
                from tqdm import tqdm  # noqa: PLC0415

                with (
                    os.fdopen(tmp_fd, "wb") as f,
                    tqdm(total=total, unit="B", unit_scale=True, desc=dest_dir.name) as pbar,
                ):
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))
            except ImportError:
                downloaded = 0
                with os.fdopen(tmp_fd, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded * 100 // total
                            logger.info("Progress: %d%%", pct)

        logger.info("Extracting to %s ...", dest_dir)
        with tarfile.open(tmp_file, "r:gz") as tar:
            tar.extractall(path=dest_dir, filter="data")

        logger.info("Download complete: %s", dest_dir)
    except Exception:
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    finally:
        tmp_file.unlink(missing_ok=True)

    return dest_dir


def ensure_synthea1k(project_root: Path | None = None) -> Path:
    """Ensure Synthea 1K test data is available locally."""
    root = project_root or Path.cwd()
    return _download_and_extract(_SYNTHEA1K_URL, root / _SYNTHEA1K_DEST)


def ensure_omop_vocabularies(project_root: Path | None = None) -> Path:
    """Ensure OMOP vocabulary files are available locally."""
    root = project_root or Path.cwd()
    return _download_and_extract(_OMOP_VOCAB_URL, root / _OMOP_VOCAB_DEST)
