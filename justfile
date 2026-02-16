set dotenv-load := true

# Default recipe: show available commands
default:
    @just --list

init:
    uv sync --all-groups --all-extras
    uv run pre-commit install

test:
    uv run pytest --cov=pluginlake

lint:
    uv run ruff check .
    uv run ty check .

secure:
    uv run uv-secure

ci: lint test secure

docs:
    uv run zensical serve

pre-commit:
    uv run pre-commit run --all-files
