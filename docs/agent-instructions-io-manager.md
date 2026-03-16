# Agent Instructions: Finish DuckLake IO Manager Implementation

Read `.github/copilot-instructions.md` before writing any code. Follow all rules there (no logic in `__init__.py`, Google-style docstrings, `get_logger(__name__)`, Polars not pandas, `uv run` for commands, etc.).

## Context

Branch: `15-ducklake-w-psql-setup`. The following files already exist and should not be recreated or significantly changed:

- `src/pluginlake/core/storage/base.py` - `StorageBackend` ABC with `get_base_path()` and `configure_duckdb()`
- `src/pluginlake/core/storage/local.py` - `LocalStorageBackend` implementation
- `src/pluginlake/core/storage/__init__.py` - docstring only
- `src/pluginlake/core/ducklake/__init__.py` - docstring only
- `src/pluginlake/core/ducklake/config.py` - `DuckLakeSettings` (Pydantic Settings, `PLUGINLAKE_DUCKLAKE_` prefix, all fields required, no defaults, `storage_backend: Literal["local"]`)
- `src/pluginlake/core/ducklake/setup.py` - `ensure_database()`, `create_connection()`, `setup_ducklake()`, `_resolve_storage_backend()`

Read each of these files first to understand the existing code before writing anything.

## Step 1: Create the DuckLake IO Manager

Create `src/pluginlake/core/ducklake/io_manager.py`.

This is a Dagster `IOManager` that persists asset outputs to DuckLake via DuckDB.

Requirements:
- Subclass `dagster.IOManager`
- Constructor takes a `duckdb.DuckDBPyConnection` (the connection returned by `setup_ducklake()`)
- The connection already has the `ducklake` catalog attached
- **`handle_output(context, obj)`**: writes asset output to DuckLake
  - `obj` is a `polars.DataFrame`
  - Derive the table name from `context.asset_key` (use the last part of the key path, e.g., `AssetKey(["condition_era"])` becomes table `condition_era`)
  - Use schema `ducklake.main` (DuckLake's default schema under the attached catalog)
  - Convert the Polars DataFrame to Arrow (`obj.to_arrow()`) and write it using DuckDB's `CREATE OR REPLACE TABLE ducklake.main.{table_name} AS SELECT * FROM arrow_table`
  - Log the table name and row count using `get_logger(__name__)`
- **`load_input(context)`**: reads a DuckLake table back as a Polars DataFrame
  - Derive table name the same way from `context.asset_key`
  - Query with `SELECT * FROM ducklake.main.{table_name}`
  - Convert result to Polars: `polars.from_arrow(conn.execute(...).fetch_arrow_table())`
- Also create a factory function decorated with `@dagster.io_manager` that:
  - Calls `setup_ducklake()` (which handles ensure DB + connect)
  - Returns a `DuckLakeIOManager` instance
  - Name it `ducklake_io_manager`

## Step 2: Register the IO Manager in Definitions

Edit `src/pluginlake/definitions/omop.py` and `src/pluginlake/definitions/fhir.py`:
- Import `ducklake_io_manager` from `pluginlake.core.ducklake.io_manager`
- Add it to `Definitions` as a resource: `Definitions(assets=[], resources={"io_manager": ducklake_io_manager})`

This makes DuckLake the default IO manager for all assets in both code locations.

## Step 3: Write Tests

Test files go under `tests/unit/pluginlake/` mirroring the source structure. Create `__init__.py` files (empty or docstring only) for any new test directories.

### `tests/unit/pluginlake/core/__init__.py` - docstring only
### `tests/unit/pluginlake/core/storage/__init__.py` - docstring only
### `tests/unit/pluginlake/core/ducklake/__init__.py` - docstring only

### `tests/unit/pluginlake/core/storage/test_local.py`
Test `LocalStorageBackend`:
- `get_base_path()` returns an absolute path string
- The directory is created on init
- `configure_duckdb()` does not raise (pass it a real `duckdb.connect()`)

### `tests/unit/pluginlake/core/ducklake/test_config.py`

Test `DuckLakeSettings`:
- Loading with all env vars set works (use `monkeypatch.setenv` for each `PLUGINLAKE_DUCKLAKE_*` var)
- Missing a required var raises `ValidationError`
- `pg_connection_string` property produces the correct format
- Invalid `storage_backend` (e.g., `"s3"`) raises `ValidationError`

### `tests/unit/pluginlake/core/ducklake/test_setup.py`
Test `_resolve_storage_backend`:
- `"local"` returns a `LocalStorageBackend`
- Anything else raises `ValueError`

Test `ensure_database` and `create_connection`:
- These need PostgreSQL and DuckLake, so **mock them**
- Use `unittest.mock.patch` to mock `psycopg2.connect` for `ensure_database`
- Mock the cursor's `fetchone` to return `None` (DB doesn't exist) and verify `CREATE DATABASE` is called
- Mock `fetchone` to return `(1,)` (DB exists) and verify `CREATE DATABASE` is NOT called
- For `create_connection`, mock `duckdb.connect` and verify the `INSTALL ducklake`, `LOAD ducklake`, and `ATTACH` calls happen

### `tests/unit/pluginlake/core/ducklake/test_io_manager.py`
Test `DuckLakeIOManager`:
- Create a real in-memory DuckDB connection (no mocks needed for DuckDB itself)
- But you need DuckLake extension for the `ducklake.main` schema, which won't be available without Postgres
- So mock at the DuckDB execute level, or test the table name derivation logic separately
- Test that `handle_output` calls the correct SQL with the right table name
- Test that `load_input` calls the correct SELECT query
- Test the `ducklake_io_manager` factory calls `setup_ducklake()`

### Important test rules:
- Write tests as plain functions, not inside classes
- Use fixtures for shared setup
- Only test our own code, not DuckDB/Polars/psycopg2 internals
- Keep tests simple, one behavior per test

## Step 4: Run Tests and Fix Errors

Run: `uv run pytest tests/unit/ -v`

Fix any import errors, assertion failures, or type issues. Also run `uv run ruff check src/ tests/` and fix any lint issues.

## Do NOT:
- Add logic to any `__init__.py` file
- Add default values to `DuckLakeSettings` fields
- Use pandas anywhere
- Use `print()` (use `get_logger(__name__)` instead)
- Create files outside the scope described above
- Modify `base.py`, `local.py`, `config.py`, or `setup.py` unless fixing a bug found during testing
