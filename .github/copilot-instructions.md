# Copilot Instructions for pluginlake

## Python

- Target Python 3.13+. Do not use `from __future__ import annotations`.
- Use native type hints (`str | None`, `list[int]`, etc.) instead of `typing` equivalents.
- Write small, focused functions. Only use nested functions or inline imports when they provide a clear benefit.
- Keep classes stateless. Use classes to group related functionality, not to hold mutable state.
- Prefer returning values over mutating arguments.
- Use `logging` via `get_logger(__name__)` from `pluginlake.utils.logger`, never `print()`.
- Use Google-style docstrings.

## Project tooling

- Always use `uv` as the package manager and task runner.
- All settings and tool configuration live in `pyproject.toml`.
- Run commands with `uv run` (e.g., `uv run pytest`, `uv run ruff check .`).
- Use `just` recipes for common tasks.

## Configuration

- Use Pydantic Settings (`pydantic-settings`) for all configuration.
- Root settings are in `pluginlake/config.py`.
- Each submodule can have its own `config.py` with a `Settings` child class.
- Keep config in config files, not scattered through business logic.

## Code organization

- `pluginlake/utils/` contains generic, reusable functions and helpers used across the project.
- Do not put reusable code inside submodules if it will be shared elsewhere.
- Each submodule should be self-contained with clear boundaries.

## Testing

- Use `pytest` for all tests.
- Only test our own code, not functionality from external packages/libraries.
- Test files mirror the source structure under `tests/unit/pluginlake/`.
- Keep tests simple and focused on one behavior per test.

## Data

- Use Polars for DataFrame operations, not pandas.
- Prefer lazy evaluation where possible.
- Only reuse data assets between pipelines if they are the exact same dataset.
