"""Tests for the shared secret helpers."""

import errno
import stat
from pathlib import Path

import pytest

from pluginlake.utils.secrets import random_password, write_secret


def test_random_password_has_every_character_class():
    password = random_password()
    assert len(password) == 24
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)
    assert any(c.isdigit() for c in password)
    assert any(not c.isalnum() for c in password)


def test_write_secret_is_private_and_never_overwrites(tmp_path: Path):
    path = tmp_path / "secret"
    assert write_secret(path, "first") is True
    assert write_secret(path, "second") is False
    assert path.read_text() == "first"
    assert stat.S_IMODE(path.stat().st_mode) == 0o400


def test_write_secret_leaves_no_partial_file_when_writing_fails(tmp_path: Path, monkeypatch):
    path = tmp_path / "secret"

    def broken_fsync(fd: int) -> None:
        message = "disk full"
        raise OSError(message)

    monkeypatch.setattr("pluginlake.utils.secrets.os.fsync", broken_fsync)
    with pytest.raises(OSError, match="disk full"):
        write_secret(path, "value")
    assert list(tmp_path.iterdir()) == []


def test_write_secret_without_hard_links_is_complete_and_never_overwrites(tmp_path: Path, monkeypatch):
    path = tmp_path / "secret"

    def no_hard_links(src: Path, dst: Path) -> None:
        raise OSError(errno.EPERM, "no hard links")

    monkeypatch.setattr("pluginlake.utils.secrets.os.link", no_hard_links)
    assert write_secret(path, "first") is True
    assert write_secret(path, "second") is False
    assert path.read_text() == "first"
    assert [p.name for p in tmp_path.iterdir()] == ["secret"]
