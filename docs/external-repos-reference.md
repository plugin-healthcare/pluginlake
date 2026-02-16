# External Repos Reference

This document captures useful code, packages, and architectural decisions from the
`external_repos/` directory before removal. These repos were prototypes and explorations
that informed the design of pluginlake.

---

## 1. dagster-data-station

**Purpose:** Dagster-orchestrated lakehouse processing CBS open data and OMOP vocabulary files
into Parquet/DuckDB.

### Packages

| Package | Version | Purpose |
|---|---|---|
| dagster | ==1.11.15 | Orchestration framework |
| dagster-polars | >=0.27.7 | PolarsParquetIOManager |
| dagster-duckdb-polars | >=0.27.15 | DuckDB + Polars IO manager |
| duckdb | >=1.4.1 | Analytical database |
| polars[pyarrow] | >=1.34.0 | DataFrames with Parquet support |
| cbsodata | >=1.3.5 | CBS open data API client |
| marimo | 0.14.10 | Notebook framework |
| pyyaml | (transitive) | YAML config parsing |

### Architecture

- **Dagster "defs folder" pattern** with `load_from_defs_folder` for auto-discovery.
- **Dynamic asset factories** driven by YAML config (CBS tables) and filesystem scanning
  (OMOP vocabulary files).
- **PolarsParquetIOManager** with per-domain base dirs for persistence.
- **Pipeline:** raw CSV/API -> Polars DataFrame -> Parquet -> DuckDB consolidation.

### Useful Snippets

**Dynamic asset factory from YAML config:**

```python
def build_cbs_job(table_id: str) -> dg.Definitions:
    asset_key = f"cbs-{table_id}"

    @dg.asset(
        name=asset_key,
        io_manager_key="cbs_polars_parquet_io_manager",
        group_name="CBS",
        kinds={"polars", "parquet"},
    )
    def build_cbs_asset(context, cbs: dg.ConfigurableResource) -> pl.DataFrame:
        return pl.DataFrame(cbs.get_data(table_id))

    return dg.Definitions(assets=[build_cbs_asset])


def load_cbs_job_from_yaml(yaml_path: str) -> dg.Definitions:
    config = yaml.safe_load(open(yaml_path))
    defs = [build_cbs_job(table) for table in config["tables"]]
    return dg.Definitions.merge(*defs)
```

**Robust CSV loading with Polars (messy healthcare data):**

```python
df = pl.read_csv(
    file_path,
    separator=separator,
    try_parse_dates=True,
    truncate_ragged_lines=True,
    ignore_errors=True,
    encoding="utf8-lossy",
    quote_char=None,
)
```

**ConfigurableResource wrapping a third-party API:**

```python
class CBSResource(dg.ConfigurableResource):
    get_info = cbsodata.get_info
    get_data = cbsodata.get_data
```

---

## 2. dhd-pluginlake

**Purpose:** FastAPI-based local data lake API for uploading/downloading Parquet files,
with YAML-driven directory scaffolding. Has two generations: `OLD/plugindb/` (complete)
and `src/pluginlake/` (scaffolded v2).

### Packages

| Package | Version | Purpose |
|---|---|---|
| fastapi | - | Web framework |
| uvicorn | - | ASGI server |
| polars | - | DataFrames |
| pyarrow | - | Parquet backend |
| pyyaml | - | YAML config |
| aiofiles | - | Async file I/O |
| python-dotenv | - | .env loading |
| python-multipart | - | File uploads |

### Architecture

- **FastAPI with global Bearer token auth middleware** (excluded paths for auth endpoints).
- **YAML-driven lake setup** - config file defines directory structures per "lake",
  `DataLakeSetup` class creates/validates them.
- **File-based storage** - Parquet files on disk, served via `FileResponse`.
- **AIOC domain class** with config-driven import/export path resolution.

### Useful Snippets

**Bearer token auth middleware pattern:**

```python
@app.middleware("http")
async def token_middleware(request: Request, call_next):
    excluded_paths = ["/auth/token", "/favicon.ico", "/"]
    if request.url.path not in excluded_paths:
        extract_and_validate_token(request)
    response = await call_next(request)
    return response
```

**Parquet file save with timestamp+UUID dedup:**

```python
def save_parquet_file(file_content: bytes, original_filename: str, directory: str) -> str:
    timestamp = int(datetime.now().timestamp())
    unique_id = uuid.uuid4()
    new_filename = f"{timestamp}_{unique_id}_{original_filename}"
    file_path = os.path.join(directory, new_filename)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return new_filename
```

**Recursive directory tree as nested dict:**

```python
def list_files_and_folders(directory: str) -> dict:
    dir_structure = {}
    for root, dirs, files in os.walk(directory):
        path = root.replace(directory, "").strip(os.sep)
        levels = path.split(os.sep) if path else []
        subdir = dir_structure
        for level in levels:
            subdir = subdir.setdefault(level, {})
        subdir["files"] = files
    return dir_structure
```

**Polars in-memory Parquet upload/download test:**

```python
df = pl.DataFrame({"column1": [10, 20, 30], "column2": ["x", "y", "z"]})
parquet_buffer = BytesIO()
df.write_parquet(parquet_buffer)
parquet_buffer.seek(0)
files = {"file": ("sample.parquet", parquet_buffer, "application/octet-stream")}
```

---

## 3. duckbtlake

**Purpose:** Hospital data lakehouse prototype combining DuckDB + DuckLake (catalog extension)
with dbt for SQL transformations. Includes medical code system extraction utilities.

### Packages

| Package | Purpose |
|---|---|
| duckdb | Core DB engine with DuckLake extension |
| polars | CSV reading for code extraction |
| dbt-duckdb | dbt adapter for DuckDB |

### Architecture

- **DuckLake as catalog** - metadata file (`metadata.ducklake`) provides lakehouse semantics.
- **dbt for SQL transformations** - staging models read external Parquet files.
- **JSON Schema for medical code systems** - unique codes extracted from reference CSVs.
- **Composite keys** - `hospital_id + patient_id + admission_id` pattern.

### Useful Snippets

**DuckDB + DuckLake connection pattern:**

```python
con = duckdb.connect()
con.install_extension("ducklake")
con.load_extension("ducklake")
con.execute("ATTACH 'ducklake:metadata.ducklake' AS lake")
con.execute("USE lake")
```

**CSV to JSON Schema code system extractor:**

```python
def extract_code_system_schema(csv_path: Path, code_column: str, out_path: Path) -> dict:
    df = pl.read_csv(str(csv_path), separator=";", schema_overrides={code_column: pl.Utf8})
    codes = df[code_column].unique().to_list()
    schema_id = str(out_path.relative_to(SCHEMAS_ROOT))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        "type": "string",
        "enum": codes,
    }
```

**ICD-10 parsing in SQL (dbt model):**

```sql
SELECT *,
    concat_ws('_',
        cast(hospital_id AS VARCHAR),
        cast(patient_id AS VARCHAR),
        cast(admission_id AS VARCHAR)
    ) AS unique_admission_id,
    regexp_extract(main_diagnosis_code, '^([^./]+)', 1) AS icd10_category,
    substr(main_diagnosis_code, 1, 1) AS icd10_chapter
FROM {{ source('lake_raw', 'admissions') }}
```

---

## 4. plugin-blob-proxy

**Purpose:** Azure Blob Storage encryption proxy using hybrid RSA + Fernet encryption.
Each hospital node runs its own proxy with unique key pairs for secure data exchange.

### Packages

| Package | Purpose |
|---|---|
| fastapi | HTTP API |
| uvicorn | ASGI server |
| cryptography | RSA, Fernet encryption |
| azure-storage-blob | Azure Blob Storage SDK |
| azure-identity | Azure AD auth (ClientSecretCredential) |
| pydantic-settings | Settings management |

### Architecture

- **Hybrid encryption:** files encrypted with Fernet (symmetric), symmetric key encrypted
  per-recipient with RSA-2048 OAEP.
- **Pydantic Settings** with `lru_cache` singleton.
- **Two Docker containers:** `keygen` (one-shot) + `server` (FastAPI).
- **Azure AD service principal auth** via `ClientSecretCredential`.
- **Custom PBKDF2-based API authentication** (not JWT/OAuth).

### Useful Snippets

**Fernet symmetric encrypt/decrypt:**

```python
from cryptography.fernet import Fernet

def symmetric_encrypt(data: bytes, key: bytes) -> bytes:
    f = Fernet(key)
    return f.encrypt(data)

def symmetric_decrypt(data: bytes, key: bytes) -> bytes:
    f = Fernet(key)
    return f.decrypt(data)
```

**RSA encrypt with OAEP padding:**

```python
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

def rsa_encrypt(data: bytes, public_key: rsa.RSAPublicKey | str) -> bytes:
    if isinstance(public_key, str):
        rsa_key = serialization.load_pem_public_key(public_key.encode())
    else:
        rsa_key = public_key
    return rsa_key.encrypt(
        data,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
```

**Multi-recipient key encryption:**

```python
def encrypt_keys(rsa_public_keys: dict[str, str], sym_key: bytes) -> dict[str, str]:
    encrypted_keys = {}
    for node_id, rsa_key in rsa_public_keys.items():
        encrypted_keys[node_id] = base64.b64encode(
            rsa_encrypt(sym_key, rsa_key)
        ).decode("utf-8")
    return encrypted_keys
```

**PBKDF2 key derivation:**

```python
def derive_key(key: str, salt: str) -> bytes:
    raw_key = hashlib.pbkdf2_hmac("sha256", key.encode(), salt.encode(), 100000, dklen=32)
    return base64.urlsafe_b64encode(raw_key)
```

---

## 5. pluginSHIRE

**Purpose:** Composable data infrastructure framework for the PLUGIN healthcare project.
Collection of container setups, prototype services, and exploration notebooks for
federated data exchange.

### Packages

| Package | Purpose |
|---|---|
| polars | DataFrames |
| duckdb | In-memory queries |
| fastapi + uvicorn | REST API for DuckDB service |
| pyiceberg | Iceberg table format (SqlCatalog with SQLite) |
| webdav4 + fsspec | WebDAV filesystem access |
| vantage6-algorithm-tools | Federated learning framework |
| pandera | DataFrame schema validation (recommended) |
| fhir.resources | FHIR resource validation (recommended) |

### Architecture

- **Apache Iceberg** (via PyIceberg) as metadata/versioning layer with local SQLite catalog.
- **WebDAV over Apache httpd** as file access protocol via `fsspec` + `webdav4`.
- **DuckDB** as in-memory query engine exposed via FastAPI.
- **vantage6** for federated algorithm execution (Docker containers on Azure Container Registry).
- **Docker bridge networks** simulating federated node setups.

### Useful Snippets

**PyIceberg round-trip with Polars:**

```python
from pyiceberg.catalog.sql import SqlCatalog

catalog = SqlCatalog(
    "default",
    uri=f"sqlite:///{warehouse_path}/pyiceberg_catalog.db",
    warehouse=f"file://{warehouse_path}",
)
catalog.create_namespace("dis")

df = pl.read_csv(url, try_parse_dates=True)
table = catalog.create_table("dis.zorgproducten", schema=df.to_arrow().schema)
table.append(df.to_arrow())

# Read back
result = pl.scan_iceberg(table).collect()
```

**WebDAV filesystem utilities:**

```python
from webdav4.fsspec import WebdavFileSystem

def get_wd_fs(url, credentials: tuple[str, str] | None = None):
    return WebdavFileSystem(base_url=url, auth=credentials)

def listdir(path: str, fs: WebdavFileSystem, detail: bool | None = False):
    return fs.ls(path, detail=detail)

def read_file(path: str, fs: WebdavFileSystem) -> str:
    with fs.open(path, "r") as f:
        return f.read()

def write_file(path: str, content: str, fs: WebdavFileSystem) -> bool:
    with fs.open(path, "w") as f:
        f.write(content)
    return read_file(path, fs) == content
```

**FastAPI + DuckDB with API key auth:**

```python
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
```

---

## Common Patterns Across Repos

| Pattern | Used In | Status in pluginlake |
|---|---|---|
| Polars + DuckDB + Parquet stack | All repos | Adopted |
| Pydantic Settings | blob-proxy, pluginlake v2 | Adopted |
| FastAPI + Uvicorn | dhd, blob-proxy, pluginSHIRE | Not yet needed |
| Dagster orchestration | dagster-data-station | Planned |
| PyIceberg / DuckLake catalog | duckbtlake, pluginSHIRE | To evaluate |
| WebDAV via fsspec | pluginSHIRE | To evaluate |
| Hybrid RSA + Fernet encryption | blob-proxy | Reference only |
| YAML-driven config/scaffolding | dagster-data-station, dhd | Partial (Pydantic Settings) |
| JSON Schema for code systems | duckbtlake | To evaluate |
| vantage6 federated execution | pluginSHIRE | Reference only |
