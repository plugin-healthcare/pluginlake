"""Tests for pluginlake.config."""

import logging

import pytest

from pluginlake.config import LogLevel, Settings


def test_defaults(settings):
    assert settings.debug is False
    assert settings.verbose is False
    assert settings.log_level == LogLevel.INFO


def test_debug_overrides_log_level():
    s = Settings(debug=True, log_level=LogLevel.WARNING)
    assert s.effective_log_level == logging.DEBUG


def test_verbose_overrides_log_level():
    s = Settings(verbose=True, log_level=LogLevel.WARNING)
    assert s.effective_log_level == logging.DEBUG


def test_effective_log_level():
    s = Settings(log_level=LogLevel.ERROR)
    assert s.effective_log_level == logging.ERROR


def test_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLUGINLAKE_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("PLUGINLAKE_DEBUG", "true")
    s = Settings()
    assert s.log_level == LogLevel.WARNING
    assert s.debug is True
