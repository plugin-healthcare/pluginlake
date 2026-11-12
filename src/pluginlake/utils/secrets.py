"""Generate secret values and write them as private files.

Shared by every deployment (compose, Kubernetes) so secrets are generated and stored the same way.
Existing files are never overwritten, so generating again is safe.
"""

import base64
import secrets
import string
from pathlib import Path

SYMBOLS = "!#%*+-=?@^_"


def random_hex(nbytes: int = 16) -> str:
    """Return a random hex string of ``2 * nbytes`` characters."""
    return secrets.token_hex(nbytes)


def random_base64(nbytes: int = 32) -> str:
    """Return a random base64 string (44 characters for 32 bytes)."""
    return base64.b64encode(secrets.token_bytes(nbytes)).decode()


def random_password(length: int = 24) -> str:
    """Return a password with upper case, lower case, a digit and a symbol."""
    pools = (string.ascii_uppercase, string.ascii_lowercase, string.digits, SYMBOLS)
    chars = [secrets.choice(pool) for pool in pools]
    chars += [secrets.choice("".join(pools)) for _ in range(length - len(pools))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def write_secret(path: Path, content: str, mode: int = 0o400) -> bool:
    """Write a secret file with a restrictive mode unless it already exists.

    Args:
        path: Destination file.
        content: Secret content.
        mode: File permissions, owner read-only by default.

    Returns:
        True if the file was created, False if it already existed.
    """
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)
    return True
