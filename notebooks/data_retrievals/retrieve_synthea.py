import marimo

__generated_with = "0.19.10"
app = marimo.App()


@app.cell
def _():
    """Download Synthea Sample Data - Pre-generated synthetic patient data."""
    from pathlib import Path

    import boto3
    import requests
    from botocore import UNSIGNED
    from botocore.config import Config
    from tqdm import tqdm

    # Local data directories
    DATA_DIR = Path(__file__).parent.parent / "data" / "synthea"
    FHIR_DIR = DATA_DIR / "fhir"
    OMOP_DIR = DATA_DIR / "omop"

    def ensure_empty_dir(path: Path) -> None:
        """Ensure directory exists and is empty, raise error if not empty."""
        path.mkdir(parents=True, exist_ok=True)
        if any(path.iterdir()):
            raise FileExistsError(f"Directory not empty: {path}")

    return (
        Config,
        FHIR_DIR,
        OMOP_DIR,
        Path,
        UNSIGNED,
        boto3,
        ensure_empty_dir,
        requests,
        tqdm,
    )


@app.cell
def _(FHIR_DIR, Path, ensure_empty_dir, requests, tqdm):
    SYNTHEA_FHIR_URL = "https://mitre.box.com/shared/static/3bo45m48ocpzp8fc0tp005vax7l93xji.gz"

    def download_fhir(url: str = SYNTHEA_FHIR_URL, chunk_size: int = 8 * 1024 * 1024) -> Path:
        """Download Synthea FHIR data (28GB tar.gz)."""
        ensure_empty_dir(FHIR_DIR)

        dest = FHIR_DIR / "synthea_full.tar.gz"
        print(f"Downloading {url} to {dest}...")

        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))

            with (
                dest.open("wb") as f,
                tqdm(total=total_size, unit="B", unit_scale=True, desc="Downloading FHIR") as pbar,
            ):
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        print(f"Downloaded: {dest}")
        return dest

    return (download_fhir,)


@app.cell
def _(Config, OMOP_DIR, Path, UNSIGNED, boto3, ensure_empty_dir, tqdm):
    S3_BUCKET = "synthea-omop"

    def download_omop() -> Path:
        """Download Synthea OMOP data from S3 (1k, 100k, 2.8m patient datasets)."""
        ensure_empty_dir(OMOP_DIR)

        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name="us-east-1")
        print(f"Listing objects in S3 bucket: {S3_BUCKET}...")

        # Collect all objects to download
        objects = []
        total_size = 0
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=S3_BUCKET):
            for obj in page.get("Contents", []):
                if not obj["Key"].endswith("/") and obj["Size"] > 0:
                    objects.append((obj["Key"], obj["Size"]))
                    total_size += obj["Size"]

        print(f"Downloading {len(objects)} files ({total_size / (1024**3):.2f} GB)...")

        with tqdm(total=total_size, unit="B", unit_scale=True, desc="Downloading OMOP") as pbar:
            for key, size in objects:
                dest = OMOP_DIR / key
                dest.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(S3_BUCKET, key, str(dest))
                pbar.update(size)

        print(f"Downloaded to: {OMOP_DIR}")
        return OMOP_DIR

    return (download_omop,)


@app.cell
def _(download_fhir):
    # Download FHIR data
    download_fhir()


@app.cell
def _(download_omop):
    # Download OMOP data
    download_omop()


@app.cell
def _(FHIR_DIR, OMOP_DIR):
    # List downloaded data
    def list_data():
        """List all downloaded Synthea data."""
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

    list_data()


if __name__ == "__main__":
    app.run()
