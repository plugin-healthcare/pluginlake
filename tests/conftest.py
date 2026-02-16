"""Shared test fixtures for pluginlake."""

import pytest

from pluginlake.config import Settings


@pytest.fixture
def settings():
    """Provide a default Settings instance."""
    return Settings()
