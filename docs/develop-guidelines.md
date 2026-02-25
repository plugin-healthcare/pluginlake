# Development guidelines for pluginlake

This guide provides information on how we develop and maintain pluginlake. It covers topics such as code style, testing, and contributing to the project.

## Design Principles

### General Python

- **Readability first** Code should be self-documenting. Prefer explicit over implicit, and clarity over cleverness.
- **Efficiency matters** Consider performance implications, especially for data-heavy operations. Profile before optimizing.
- **Type everything** Use type hints consistently. They catch bugs early and serve as documentation.
- **Fail fast** Validate inputs early and raise meaningful errors. Don't let invalid state propagate.

### Configuration

- Use **Pydantic Settings** (`pydantic-settings`) for all configuration management.
- Load configuration from environment variables with sensible defaults.
- Validate configuration at startup, not at runtime.
- **Modular settings** Each submodule can define its own `Settings` child class. This keeps configuration scoped and composable:

```python
# pluginlake/config.py (root settings)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    debug: bool = False
    log_level: str = "INFO"

# pluginlake/core/config.py (submodule settings)
from pydantic_settings import BaseSettings, SettingsConfigDict

class DuckLakeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DUCKLAKE_")

    pg_host: str
    pg_user: str
```

### Modularity

- **Design for composability** Each module should be self-contained with clear boundaries.
- **Single responsibility** A module and its functions should do one thing well. If it's doing too much, split it.
- **Dependency injection** Pass dependencies explicitly rather than importing globals. This improves testability.
- **Avoid tight coupling** Modules should depend on abstractions (protocols/interfaces), not concrete implementations where practical.

### APIs

- Use **FastAPI** for all HTTP endpoints.
- Follow REST conventions for resource naming and HTTP methods.
- Use Pydantic models for request/response validation.
- Document endpoints with OpenAPI (FastAPI does this automatically).

### Data Pipelines

- **Only reuse assets if they represent the exact same dataset** Don't share assets between pipelines just because they look similar. Each pipeline should own its data transformations.
- Use **Polars** for DataFrame operations because it's faster and more memory-efficient than pandas.
- Prefer lazy evaluation where possible to minimize memory footprint.
- Document data schemas and transformations clearly.

### Dependencies

- Keep dependencies minimal and intentional.
- Pin versions in `pyproject.toml` with minimum bounds (e.g., `>=1.0.0`).
- Review new dependencies for maintenance status and security.

## Code Style

Coding rules are defined in [`.github/copilot-instructions.md`](../.github/copilot-instructions.md). These are automatically picked up by GitHub Copilot and serve as the single source of truth for coding conventions. Key rules:

- Target Python 3.13+. Do not use `from __future__ import annotations`.
- Use native type hints (`str | None`, `list[int]`), not `typing` equivalents.
- Write small, focused functions. Keep classes stateless.
- Prefer returning values over mutating arguments.
- Use `get_logger(__name__)` for logging, never `print()`.
- Use Google-style docstrings.
- Keep config in config files using Pydantic Settings.
- Put reusable code in `pluginlake/utils/`, not in submodules.
- Only test our own code, not external package behavior.

We use ruff as our all-in-one linter and formatter:

```bash
uv run ruff check .
```

We also use ty for type checking to catch type-related errors before they happen. You can run ty locally using the following command:

```bash
uv run ty check .
```

> :bulb: most code editors have plugins for ruff and ty that can provide real-time feedback on code style and type issues, so we recommend setting those up for a smoother development experience.

## Documentation

For documentation, we use [zensical](https://zensical.org/) to create and maintain our project documentation. Documentation is automatically generated and deployed to GitHub Pages. To build the documentation locally, you can use the following command:

```bash
uv run zensical build
```

and to serve it locally:

```bash
uv run zensical serve
```

Besides manual documentation, we also use docstrings in our code to provide inline documentation for functions, classes, and modules. We follow the [Google style guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) for writing docstrings.

## Testing

We use [pytest](https://docs.pytest.org/en/stable/) as our testing framework. We write unit tests for our code to ensure that it works as expected and to catch any regressions. To run the tests, you can use the following command:

```bash
uv run pytest
```

## CI/CD

### Pre-commit hooks

For local development, we use pre-commit to run linters and formatters before each commit. This helps maintain code quality and consistency. To set up pre-commit hooks, run:

```bash
pre-commit install
```

All pre-commit hooks are defined in the `.pre-commit-config.yaml` file and include:
- Trailing whitespace removal
- End-of-file fixer
- YAML/TOML validation
- Large file checks
- Ruff linting and formatting
- ty type checking

### GitHub Actions

We use GitHub Actions to automate our CI/CD pipeline. All workflows are defined in the `.github/workflows` directory.

#### CI Workflow (`ci.yaml`)

Runs on every push and pull request to `main` and `dev`:
- **Ruff check** linting only (no auto-fixing)
- **Pytest**: Unit tests on all python code

#### Security Workflow (`security.yaml`)

- Runs **daily at 06:00 UTC** on the default branch
- Also runs on push to `dev`
- Checks for security vulnerabilities using `uv-secure`

#### Docker Build Workflow (`docker-build.yaml`)

Automatically builds and pushes Docker images to Azure Container Registry when relevant files change:
- Triggers on push to `main` or `dev` when `src/`, `deploy/docker/`, `pyproject.toml`, or `uv.lock` change
- Uses path filtering to only rebuild affected images
- Tags: `latest` (main), `dev` (dev branch), and commit SHA
- Includes SLSA provenance and SBOM attestations

#### Dependabot

Dependabot is configured to check daily for updates to:
- Python dependencies
- GitHub Actions versions
- Docker base images

All update PRs target the `dev` branch.
