"""Tests for the images lock of the packaged production stack."""

import json
from pathlib import Path

import pytest

from pluginlake.deploy import images
from pluginlake.deploy.images import IMAGE_NAMES, ImageLockError, load_image_lock, released_image_env, write_image_lock

DIGESTS = {name: "sha256:" + str(i) * 64 for i, name in enumerate(IMAGE_NAMES, start=1)}


@pytest.fixture
def lock_path(tmp_path: Path) -> Path:
    return tmp_path / "images.json"


def test_write_and_load_roundtrip(lock_path: Path):
    write_image_lock("0.2.0", DIGESTS, lock_path)
    lock = load_image_lock(lock_path)
    assert lock.version == "0.2.0"
    assert lock.images["api"] == f"ghcr.io/plugin-healthcare/pluginlake/api:0.2.0@{DIGESTS['api']}"


def test_compose_env_names(lock_path: Path):
    env = write_image_lock("0.2.0", DIGESTS, lock_path).compose_env()
    assert set(env) == {
        "PLUGINLAKE_IMAGE_API",
        "PLUGINLAKE_IMAGE_DAGSTER_WEBSERVER",
        "PLUGINLAKE_IMAGE_UI_CENTRAL",
        "PLUGINLAKE_IMAGE_UI_DATASTATION",
    }


@pytest.mark.parametrize("digest", ["sha256:abc", "latest", "sha512:" + "a" * 64])
def test_write_rejects_malformed_digest(lock_path: Path, digest: str):
    with pytest.raises(ImageLockError, match="malformed"):
        write_image_lock("0.2.0", {**DIGESTS, "api": digest}, lock_path)
    assert not lock_path.exists()


def test_write_rejects_incomplete_lock(lock_path: Path):
    with pytest.raises(ImageLockError, match="missing: ui-central"):
        write_image_lock("0.2.0", {k: v for k, v in DIGESTS.items() if k != "ui-central"}, lock_path)


def test_load_rejects_tag_only_reference(lock_path: Path):
    refs = {name: f"ghcr.io/plugin-healthcare/pluginlake/{name}:0.2.0@{d}" for name, d in DIGESTS.items()}
    refs["api"] = "ghcr.io/plugin-healthcare/pluginlake/api:0.2.0"
    lock_path.write_text(json.dumps({"version": "0.2.0", "images": refs}), encoding="utf-8")
    with pytest.raises(ImageLockError, match="sha256"):
        load_image_lock(lock_path)


def test_load_rejects_other_registry(lock_path: Path):
    refs = {name: f"ghcr.io/plugin-healthcare/pluginlake/{name}:0.2.0@{d}" for name, d in DIGESTS.items()}
    refs["api"] = f"docker.io/evil/api:0.2.0@{DIGESTS['api']}"
    lock_path.write_text(json.dumps({"version": "0.2.0", "images": refs}), encoding="utf-8")
    with pytest.raises(ImageLockError):
        load_image_lock(lock_path)


def test_released_env_fails_on_empty_lock(lock_path: Path):
    lock_path.write_text('{"version": null, "images": {}}', encoding="utf-8")
    with pytest.raises(ImageLockError, match="no released images"):
        released_image_env(lock_path)


def test_released_env_fails_on_version_mismatch(lock_path: Path, monkeypatch: pytest.MonkeyPatch):
    write_image_lock("0.2.0", DIGESTS, lock_path)
    monkeypatch.setattr(images, "package_version", lambda _name: "0.3.0")
    with pytest.raises(ImageLockError, match="installed"):
        released_image_env(lock_path)


def test_released_env_accepts_normalized_prerelease(lock_path: Path, monkeypatch: pytest.MonkeyPatch):
    write_image_lock("0.2.0-rc.1", DIGESTS, lock_path)
    monkeypatch.setattr(images, "package_version", lambda _name: "0.2.0rc1")
    assert released_image_env(lock_path)["PLUGINLAKE_IMAGE_API"].endswith(DIGESTS["api"])


def test_packaged_lock_is_valid():
    load_image_lock()


def test_cli_writes_lock(lock_path: Path):
    args = ["write", "--version", "0.2.0", "--output", str(lock_path)]
    for name, digest in DIGESTS.items():
        args += ["--digest", f"{name}={digest}"]
    assert images.main(args) == 0
    assert load_image_lock(lock_path).version == "0.2.0"


def test_cli_fails_on_bad_digest(lock_path: Path):
    assert images.main(["write", "--version", "0.2.0", "--output", str(lock_path), "--digest", "api=x"]) == 1
