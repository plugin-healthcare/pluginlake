# Contributing to pluginlake

Thanks for your interest in contributing to pluginlake!
This guide covers the essentials for getting started.
For detailed technical standards (code style, testing, CI), see the [development guidelines](docs/development/develop-guidelines.md).

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (package manager and task runner)
- [just](https://github.com/casey/just) (command runner)
- Docker and Docker Compose

## Getting started

```bash
# Clone the repository
git clone https://github.com/plugin-healthcare/pluginlake.git
cd pluginlake

# Install dependencies
uv sync

# Install pre-commit hooks
pre-commit install

# Run tests to verify setup
uv run pytest

# Run linting
uv run ruff check .
```

## Branching

We use GitHub Flow with a single long-lived branch:

- `main` is always deployable (protected, requires PR review).
- Create feature branches from `main`, named `<category>/<description>`:
  - `feat/cli-module`
  - `fix/port-mismatch`
  - `docs/adrs-changelog`

## Making changes

1. Create a branch from `main`.
2. Make your changes in small, focused commits.
3. Run linting and tests before pushing:
   ```bash
   uv run ruff check .
   uv run ty check .
   uv run pytest
   ```
4. Open a pull request against `main`.

## Pull request expectations

- Describe what the PR does and why.
- Keep PRs focused — one logical change per PR.
- Ensure CI passes (linting, tests).
- Update documentation if your change affects user-facing behavior.
- Update `CHANGELOG.md` under `[Unreleased]` if the change is notable.

## Commit messages

Write clear commit messages. No strict format enforced, but prefer:

- A concise subject line (imperative mood, e.g., "Add CLI init command")
- A body explaining *why* if the change isn't obvious

## Versioning

We follow [Semantic Versioning](https://semver.org/).
Documentation-only changes, CI updates, and test additions do not bump the version.
See the [release process](docs/development/develop-guidelines.md#release-process) for details.

## Reporting issues

- Use GitHub Issues for bugs and feature requests.
- Include steps to reproduce for bugs.
- Check existing issues before creating a new one.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
