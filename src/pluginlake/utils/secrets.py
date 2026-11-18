"""Generate secret values and write them as private files.

Shared by every deployment (compose, Kubernetes) so secrets are generated and stored the same way.
Generated secrets are never overwritten, so generating again is safe.
"""

import base64
import errno
import os
import secrets
import string
import tempfile
from pathlib import Path

SYMBOLS = "!#%*+-=?@^_"
_NO_HARD_LINKS = {errno.EPERM, errno.ENOTSUP, errno.EXDEV, errno.EMLINK}


def random_hex(nbytes: int = 16) -> str:
    """Return a random hex string of ``2 * nbytes`` characters."""
    return secrets.token_hex(nbytes)


def random_base64(nbytes: int = 32) -> str:
    """Return a random base64 string (44 characters for 32 bytes)."""
    return base64.b64encode(secrets.token_bytes(nbytes)).decode()


def random_password(length: int = 24) -> str:
    """Return a password with upper case, lower case, a digit and a symbol."""
    pools = (string.ascii_uppercase, string.ascii_lowercase, string.digits, SYMBOLS)
    chars: list[str] = [secrets.choice(pool) for pool in pools]
    chars += [secrets.choice("".join(pools)) for _ in range(length - len(pools))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _staged(path: Path, content: str, mode: int) -> Path:
    """Write ``content`` to a new private file next to ``path`` and flush it to disk."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    staging = Path(name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return staging


def write_secret(path: Path, content: str, mode: int = 0o400) -> bool:
    """Write a secret file with a restrictive mode unless it already exists.

    The content is written to a staging file first and then linked into place, so ``path`` either holds the complete
    content or does not exist, also when the process is killed halfway.
    On a filesystem without hard links the staging file is renamed into place instead, so concurrent writers of one
    file must then hold a shared lock, as ``pluginlake setup`` does.

    Args:
        path: Destination file.
        content: Secret content.
        mode: File permissions, owner read-only by default.

    Returns:
        True if the file was created, False if it already existed.
    """
    if path.exists():
        return False
    staging = _staged(path, content, mode)
    try:
        os.link(staging, path)
    except FileExistsError:
        return False
    except OSError as exc:
        if exc.errno not in _NO_HARD_LINKS:
            raise
        if path.exists():
            return False
        staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)
    return True


def replace_secret(path: Path, content: str, mode: int = 0o400) -> bool:
    """Atomically replace a secret file when its content differs.

    Meant for files derived from other secrets, which must follow their source.

    Args:
        path: Destination file.
        content: Secret content.
        mode: File permissions, owner read-only by default.

    Returns:
        True if the file was created or replaced, False if it already held ``content``.
    """
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    staging = _staged(path, content, mode)
    try:
        staging.replace(path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return True
