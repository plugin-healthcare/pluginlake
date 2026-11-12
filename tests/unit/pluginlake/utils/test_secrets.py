"""Tests for the shared secret helpers."""

import stat
from pathlib import Path

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
