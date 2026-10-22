"""Tests for the core lineage sensor definitions."""

from pluginlake.core.lineage.config import LineageSettings
from pluginlake.definitions.lineage import lineage_definitions


def test_no_sensor_without_lineage_url():
    defs = lineage_definitions(LineageSettings(url=None))
    assert not defs.get_repository_def().sensor_defs


def test_sensor_registered_with_lineage_url():
    defs = lineage_definitions(LineageSettings(url="http://marquez:5000"))
    assert [s.name for s in defs.get_repository_def().sensor_defs] == ["openlineage_sensor"]
