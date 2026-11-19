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

Coding rules are defined in [`.github/copilot-instructions.md`](../../.github/copilot-instructions.md). These are automatically picked up by GitHub Copilot and serve as the single source of truth for coding conventions. Key rules:

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

## Branching and Releases

For branch naming and the basic contribution flow, see [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Branch strategy

We use GitHub Flow: one long-lived branch (`main`) with short-lived feature branches.

| Branch | Purpose |
|--------|---------|
| `main` | Always deployable. Protected, requires PR review. |
| Feature branches | Short-lived, branched from `main`. Named `<category>/<description>` (e.g., `docs/adrs-changelog`, `feat/cli-module`, `fix/port-mismatch`). |

Releases are tagged commits on `main`, not separate branches.

### Versioning

We follow [Semantic Versioning](https://semver.org/):

- **Patch** (`0.1.x`): bug fixes, security bumps, small corrections.
- **Minor** (`0.x.0`): new features, new modules, non-breaking changes to the package.
- **Major** (`x.0.0`): breaking changes to public APIs or data formats.

**What does NOT bump the version:**

- Documentation-only changes (deployed continuously via GitHub Pages).
- CI/CD workflow updates.
- Test additions or refactors with no code change.
- ADRs and design specs.

**What bumps the version:**

- Any change to `src/pluginlake/` that affects behavior.
- Dependency updates that change runtime behavior.
- Docker image changes that affect deployment.

### Release process

1. Make sure `CHANGELOG.md` has an `[Unreleased]` section describing all changes since the last release.
2. Update the version in `pyproject.toml`, rename `[Unreleased]` to `[x.y.z] — YYYY-MM-DD` (the date you tag) and add a fresh empty `[Unreleased]` above it.
3. Merge to `main` via PR (the version bump can be part of the feature PR that completes the milestone).
4. Tag the merge commit with `git tag vx.y.z && git push --tags` and create a GitHub Release from the tag.

### Changelog conventions

We follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with the categories Added, Changed, Deprecated, Removed, Fixed and Security.
Write entries from the user's perspective and add them to `[Unreleased]` in the PR itself.

## AI-assisted contributions

We follow the [Linux Foundation policy on generative AI](https://www.linuxfoundation.org/legal/generative-ai): AI-generated code is treated the same as any other contribution.

### Rules

1. **You own your commits.** The contributor is fully responsible for every line they commit, regardless of whether AI assisted in writing it. Review, understand, and validate before committing.
2. **License compliance.** Ensure the AI tool's terms do not conflict with our Apache-2.0 license. If the output includes identifiable third-party code, verify it is compatibly licensed and provide attribution.
3. **No special process.** AI-assisted contributions go through the same PR review as any other change.

### Agent configuration

Agent-agnostic instructions live in [`AGENTS.md`](../../AGENTS.md), and [`.github/copilot-instructions.md`](../../.github/copilot-instructions.md) references it.
Keep `AGENTS.md` short and state hard rules and project facts an agent cannot infer from the code.
Link to detailed instruction files instead of repeating docs, and leave out anything that is in `pyproject.toml`, the linter config or the code.

## Development stack

`just up` is the production stack that every node runs, also on a laptop with a `.localhost` domain, and it is the right choice for trying out a project or an asset.
The development stack is for changing the platform itself:

- `just dev-up` starts the dev compose with source mounts, so the API reloads with `uvicorn --reload` and Dagster runs `dagster dev`.
- `just dev-up-headless` does the same without the dashboards, and `just dev-down` stops it.
- `just dev-local` runs the Titanic example without Docker, see the [Titanic tutorial](titanic-tutorial.md).

Do not use the development stack to run a station.
It has no login in front of the applications and keeps its data in Docker volumes.

## CI/CD

### Pre-commit hooks

Run `pre-commit install` once to run the hooks from `.pre-commit-config.yaml` (whitespace, YAML/TOML validation, Ruff, ty) before each commit.

### GitHub Actions

Workflows are in `.github/workflows`:

- **`ci.yaml`** runs on every pull request to `main`: Ruff check, ty check and pytest with coverage.
- **`security.yaml`** runs daily at 06:00 UTC and on demand, and checks for vulnerabilities with `uv-secure`.
- **`docker-build.yaml.disabled`** is a scaffold for pushing the production images to Azure Container Registry. It needs auth configured before it is enabled.
- **Dependabot** checks daily for updates to Python dependencies, GitHub Actions and Docker base images, with PRs against `main`.
