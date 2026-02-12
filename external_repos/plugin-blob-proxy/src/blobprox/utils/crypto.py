import base64
import hashlib
import json
import os
from datetime import datetime

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def read_rsa_private(key_path: str) -> rsa.RSAPrivateKey:
    """Load an RSA private key from a file."""
    with open(key_path, "rb") as key_file:
        key_file = key_file.read()
    try:
        return serialization.load_pem_private_key(key_file, password=None, backend=default_backend())
    except ValueError as e:
        raise ValueError(f"Error loading RSA private key from {key_path}: {e}") from e


def read_symmetric_key(key_path: str, encode: bool = False) -> bytes:
    """Load a symmetric key from a file and return the decoded key."""
    with open(key_path, encoding="utf-8") as key_file:
        key_base64 = key_file.read().strip()
    try:
        return key_base64.encode("utf-8")
    except ValueError as e:
        raise ValueError(f"Error decoding symmetric key from {key_path}: {e}") from e


def encrypt_keys(rsa_public_keys: dict[str, str], sym_key: bytes) -> dict[str, str]:
    """Encrypt the symmetric key with the RSA public keys and outputs as utf-8 string."""
    encrypted_keys = {}
    for node_id, rsa_key in rsa_public_keys.items():
        try:
            encrypted_keys[node_id] = base64.b64encode(rsa_encrypt(sym_key, rsa_key)).decode("utf-8")
        except Exception:
            raise
    return encrypted_keys


def read_rsa_public(key_path: str) -> rsa.RSAPublicKey:
    """Load an RSA public key from a file."""
    with open(key_path, "rb") as key_file:
        key_file = key_file.read()
    try:
        return serialization.load_pem_public_key(key_file, backend=default_backend())
    except ValueError as e:
        raise ValueError(f"Error loading RSA public key from {key_path}: {e}") from e


def rsa_encrypt(data: bytes, public_key: rsa.RSAPublicKey | str) -> bytes:
    """Load pem and encrypt data using an RSA public key."""
    if isinstance(public_key, str):
        rsa_key = load_rsa_public(public_key)
    else:
        rsa_key = public_key
    return rsa_key.encrypt(
        data, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )


def rsa_decrypt(data: bytes | str, private_key: rsa.RSAPrivateKey | str) -> bytes:
    """Decrypt data using an RSA private key.

    If private_key is a string, it's loaded to an RSAPrivateKey object.
    Otherwise, it's assumed to be already an RSAPrivateKey.
    """
    if isinstance(data, str):
        data = base64.b64decode(data)

    if isinstance(private_key, str):
        rsa_key = load_rsa_private(private_key)
    else:
        rsa_key = private_key
    return rsa_key.decrypt(
        data, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )


def load_rsa_public(key_str: str) -> rsa.RSAPublicKey:
    """Load an RSA public key from a string."""
    try:
        return serialization.load_pem_public_key(key_str.encode(), backend=default_backend())
    except ValueError as e:
        raise ValueError(f"Error loading RSA public key from string: {e}") from e


def load_rsa_private(key_str: str) -> rsa.RSAPrivateKey:
    """Load an RSA private key from a string."""
    try:
        return serialization.load_pem_private_key(key_str.encode(), password=None, backend=default_backend())
    except ValueError as e:
        raise ValueError(f"Error loading RSA private key from string: {e}") from e


def symmetric_decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt data using a symmetric key."""
    f = Fernet(key)
    return f.decrypt(data)


def symmetric_encrypt(data: bytes, key: bytes) -> bytes:
    """Encrypt data using a symmetric key."""
    f = Fernet(key)
    return f.encrypt(data)


def generate_credentials(dir: str, key_id: str) -> dict:
    """Generate salt, encryption key and api key and write to file"""
    if os.path.exists(dir):
        salt = os.urandom(16).hex()
        decryption_key = Fernet.generate_key().decode()
        key = Fernet.generate_key().decode()
        credentials = {
            "salt": salt,
            "decryption_key": decryption_key,
            "key": key,
        }
        with open(f"{dir}/{key_id}.json", "w") as f:
            json.dump(credentials, f)

        return credentials
    raise ValueError("Path does not exist")


def derive_key(key: str, salt: str) -> bytes:
    """Derive a Fernet-compatible key using key and salt"""
    raw_key = hashlib.pbkdf2_hmac("sha256", key.encode(), salt.encode(), 100000, dklen=32)
    return base64.urlsafe_b64encode(raw_key)


def decrypt_key(encrypted_key: str, decryption_key: str, salt: str) -> str:
    """Decrypt the encrypted key using decryption key and salt"""
    derived_key = derive_key(decryption_key, salt)
    f = Fernet(derived_key)
    return f.decrypt(encrypted_key.encode()).decode()


def generate_encrypted_key(creds: dict[str, str], dir: str, key_id: str) -> str:
    """Generate an encrypted key based on credentials and write to file"""
    if os.path.exists(dir):
        derived_key = derive_key(creds["decryption_key"], creds["salt"])
        f = Fernet(derived_key)
        encrypted_key = f.encrypt(creds["key"].encode()).decode()
        with open(f"{dir}/{key_id}_encrypted.key", "w") as f:
            f.write(encrypted_key)

        return encrypted_key
    raise ValueError("Path does not exist")


def main() -> None:
    """Generate credentials and encrypted key"""
    secrets_path = ".secrets"
    cur_dt_int = int(datetime.now().timestamp())
    key_id = f"{cur_dt_int}_blobprox"
    creds = generate_credentials(secrets_path, key_id)
    generate_encrypted_key(creds, secrets_path, key_id)


if __name__ == "__main__":
    main()
