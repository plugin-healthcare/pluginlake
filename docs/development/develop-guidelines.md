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

1. Ensure `CHANGELOG.md` is up to date with an `[Unreleased]` section describing all changes since the last release.
2. Update the version in `pyproject.toml`.
3. Rename `[Unreleased]` to `[x.y.z] — YYYY-MM-DD` in the changelog (use today's date — the release date is when you tag, not when the code was merged).
4. Add a fresh empty `[Unreleased]` section above it.
5. Commit the version bump (can be part of the feature PR that completes the milestone, or a separate small PR).
6. Merge to `main` via PR.
7. Tag the merge commit: `git tag vx.y.z && git push --tags`.
8. Create a GitHub Release from the tag (copies changelog entry as release notes).

### Changelog conventions

We follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Use these categories:

- **Added** for new features or files.
- **Changed** for changes in existing functionality.
- **Deprecated** for soon-to-be removed features.
- **Removed** for removed features or files.
- **Fixed** for bug fixes.
- **Security** for vulnerability fixes.

Write entries from the user's perspective. Reference ADRs or PRs where helpful.

**Workflow:**

- Add entries to `[Unreleased]` as you merge PRs (in the PR itself, or right after).
- When releasing, move entries from `[Unreleased]` into the new version section.
- The tag should point to the commit that contains the changelog update, so the tagged state is self-documenting.

## AI-assisted contributions

We follow the [Linux Foundation policy on generative AI](https://www.linuxfoundation.org/legal/generative-ai): AI-generated code is treated the same as any other contribution.

### Rules

1. **You own your commits.** The contributor is fully responsible for every line they commit, regardless of whether AI assisted in writing it. Review, understand, and validate before committing.
2. **License compliance.** Ensure the AI tool's terms do not conflict with our Apache-2.0 license. If the output includes identifiable third-party code, verify it is compatibly licensed and provide attribution.
3. **No special process.** AI-assisted contributions go through the same PR review as any other change.

### Agent configuration

- Agent-agnostic coding instructions live in [`AGENTS.md`](../../AGENTS.md) at the repository root.
- GitHub Copilot-specific configuration is in [`.github/copilot-instructions.md`](../../.github/copilot-instructions.md), which references `AGENTS.md`.
- Other AI tools (Cursor, Claude, etc.) should follow `AGENTS.md` directly.

### Writing good agent instructions

Keep `AGENTS.md` short and precise (under 50 lines). Long instruction files dilute signal because agents lose focus when given too much context at once.

**Principles:**

- State hard rules (what to always/never do), not tutorials.
- Include project-specific facts an agent cannot infer from code alone (e.g., "use `uv`, not `pip`" or "always read `pyproject.toml` for linting settings").
- Use hierarchical linking: a top-level file links to domain-specific instruction files that load contextually.
- Prefer showing one correct example over explaining in prose.

**What to include in the top-level file:**

- What the project is (one sentence).
- Repository layout (condensed tree).
- Hard rules (5-10 bullet points max).
- Links to detailed instruction files.

**What belongs in separate instruction files** (e.g., `.github/instructions/*.md`):

- Language conventions with examples (Python style, type annotations).
- Framework-specific patterns (Dagster assets, pipeline structure).
- Deployment and infrastructure context (secrets, known issues).

These files can use `applyTo` patterns so agents only load them when relevant (e.g., Python rules only when editing `*.py`).

**What NOT to put in agent instructions:**

- Anything the agent can infer from `pyproject.toml`, linter config, or existing code.
- Full API documentation or runbooks. Link to docs instead.
- Frequently changing information (versions, URLs) that goes stale fast.

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

Runs on every push and pull request to `main`:
- **Ruff check** linting only (no auto-fixing)
- **Pytest**: Unit tests on all python code

#### Security Workflow (`security.yaml`)

- Runs **daily at 06:00 UTC** on the default branch
- Can also be triggered manually via workflow dispatch
- Checks for security vulnerabilities using `uv-secure`

#### Docker Build Workflow (`docker-build.yaml.disabled`)

A disabled scaffold for building and pushing the production images to Azure Container Registry. It is kept with a `.disabled` extension so GitHub does not run it, and needs auth configured (OIDC recommended for a public repo) before being enabled. When enabled it will:
- Trigger on push to `main` when `src/`, `deploy/docker/`, `pyproject.toml`, or `uv.lock` change
- Build all images (`pluginlake/pluginlake`, `pluginlake/dagster-webserver`, `pluginlake/ui-central`, `pluginlake/ui-datastation`)
- Tag: `latest` and commit SHA
- Include SLSA provenance and SBOM attestations

#### Dependabot

Dependabot is configured to check daily for updates to:
- Python dependencies
- GitHub Actions versions
- Docker base images

All update PRs target the `main` branch.
