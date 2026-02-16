"""Tests for pluginlake.config."""

import logging

from pluginlake.config import Settings


class TestSettings:
    def test_defaults(self, settings):
        assert settings.debug is False
        assert settings.verbose is False
        assert settings.log_level == "INFO"

    def test_debug_overrides_log_level(self):
        s = Settings(debug=True, log_level="WARNING")
        assert s.effective_log_level == logging.DEBUG

    def test_verbose_overrides_log_level(self):
        s = Settings(verbose=True, log_level="WARNING")
        assert s.effective_log_level == logging.DEBUG

    def test_effective_log_level(self):
        s = Settings(log_level="ERROR")
        assert s.effective_log_level == logging.ERROR

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("PLUGINLAKE_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("PLUGINLAKE_DEBUG", "true")
        s = Settings()
        assert s.log_level == "WARNING"
        assert s.debug is True
