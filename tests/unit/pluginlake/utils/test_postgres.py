"""Tests for the shared PostgreSQL helpers."""

from unittest.mock import MagicMock

import pytest

from pluginlake.utils import postgres


@pytest.fixture
def cursor(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    conn = MagicMock()
    monkeypatch.setattr(postgres.psycopg2, "connect", MagicMock(return_value=conn))
    return conn.cursor.return_value.__enter__.return_value


def _ensure() -> bool:
    return postgres.ensure_database(host="h", port=5432, user="u", password="p", dbname="dagster")  # noqa: S106


def test_existing_database_is_not_created(cursor: MagicMock):
    cursor.fetchone.return_value = (1,)
    assert _ensure() is False
    assert cursor.execute.call_count == 1


def test_missing_database_is_created(cursor: MagicMock):
    cursor.fetchone.return_value = None
    assert _ensure() is True
    assert cursor.execute.call_count == 2
