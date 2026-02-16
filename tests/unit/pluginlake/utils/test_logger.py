"""Tests for pluginlake.utils.logger."""

import logging

from pluginlake.utils.logger import get_logger, setup_logging


def test_returns_namespaced_logger():
    logger = get_logger("pluginlake.storage")
    assert logger.name == "pluginlake.storage"


def test_prefixes_non_pluginlake_name():
    logger = get_logger("storage")
    assert logger.name == "pluginlake.storage"


def test_does_not_double_prefix():
    logger = get_logger("pluginlake.pipelines.omop")
    assert logger.name == "pluginlake.pipelines.omop"


def test_clears_existing_handlers():
    setup_logging()
    setup_logging()
    root = logging.getLogger("pluginlake")
    assert len(root.handlers) == 1


def test_output_format(capsys):
    setup_logging(level=logging.INFO)
    logger = get_logger("pluginlake.test")
    logger.info("hello world")
    captured = capsys.readouterr()
    assert "| INFO     | pluginlake.test | hello world" in captured.err
