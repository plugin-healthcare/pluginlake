"""Tests for pluginlake.omop.provisioning."""

from pathlib import Path
from unittest.mock import patch

from pluginlake.omop.provisioning import ensure_omop_vocabularies


def test_calls_download_with_settings_defaults(monkeypatch):
    monkeypatch.delenv("OMOP_VOCABULARY_DIR", raising=False)
    monkeypatch.delenv("OMOP_VOCABULARY_URL", raising=False)

    with patch("pluginlake.omop.provisioning.download_and_extract") as mock_dl:
        mock_dl.return_value = Path(".data/omop_vocabularies")
        result = ensure_omop_vocabularies()

    mock_dl.assert_called_once()
    url, dest = mock_dl.call_args.args
    assert "omop_vocabularies" in url
    assert "omop_vocabularies" in str(dest)
    assert result == Path(".data/omop_vocabularies")


def test_dest_dir_overrides_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("OMOP_VOCABULARY_DIR", raising=False)
    custom = tmp_path / "custom_vocab"

    with patch("pluginlake.omop.provisioning.download_and_extract") as mock_dl:
        mock_dl.return_value = custom
        result = ensure_omop_vocabularies(dest_dir=custom)

    _, dest = mock_dl.call_args.args
    assert dest == custom
    assert result == custom


def test_uses_configured_url(monkeypatch):
    monkeypatch.setenv("OMOP_VOCABULARY_URL", "https://example.com/vocab.tar.gz")

    with patch("pluginlake.omop.provisioning.download_and_extract") as mock_dl:
        mock_dl.return_value = Path(".data/omop_vocabularies")
        ensure_omop_vocabularies()

    url, _ = mock_dl.call_args.args
    assert url == "https://example.com/vocab.tar.gz"
