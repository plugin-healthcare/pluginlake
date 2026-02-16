"""Tests for pluginlake.utils.logger."""

import logging

from pluginlake.utils.logger import get_logger, setup_logging


class TestGetLogger:
    def test_returns_namespaced_logger(self):
        logger = get_logger("pluginlake.storage")
        assert logger.name == "pluginlake.storage"

    def test_prefixes_non_pluginlake_name(self):
        logger = get_logger("storage")
        assert logger.name == "pluginlake.storage"

    def test_does_not_double_prefix(self):
        logger = get_logger("pluginlake.pipelines.omop")
        assert logger.name == "pluginlake.pipelines.omop"


class TestSetupLogging:
    def test_clears_existing_handlers(self):
        setup_logging()
        setup_logging()
        root = logging.getLogger("pluginlake")
        assert len(root.handlers) == 1

    def test_output_format(self, capsys):
        setup_logging(level=logging.INFO)
        logger = get_logger("pluginlake.test")
        logger.info("hello world")
        captured = capsys.readouterr()
        assert "| INFO     | pluginlake.test | hello world" in captured.err
