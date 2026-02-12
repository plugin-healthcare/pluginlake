import argparse
import base64
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

argparser = argparse.ArgumentParser(description="Generate RSA keys and a symmetric key for plugin-blob-proxy.")
argparser.add_argument(
    "-p",
    "--keys-dir",
    help="absolute path to directory to store keys",
)
args = argparser.parse_args()

if not args.keys_dir:
    raise Exception("keys directory not provided, use --keys-dir to specify a directory")

KEYS_DIR = args.keys_dir
if not os.path.exists(KEYS_DIR):
    print(f"key directory {KEYS_DIR} does not exist, creating it")
    os.makedirs(KEYS_DIR, exist_ok=True)

print(f"Generating keys in {KEYS_DIR}...")
# Define key file paths
private_key_path = os.path.join(KEYS_DIR, "rsa_private_key.pem")
public_key_path = os.path.join(KEYS_DIR, "rsa_public_key.pem")
symmetric_key_path = os.path.join(KEYS_DIR, "symmetric_key.key")

# Generate RSA keys if they don't exist
if not os.path.exists(private_key_path):
    # Generate RSA private key (2048 bits)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Save private key in PEM format
    try:
        with open(private_key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        print(f"private key generated and saved in {private_key_path}")
    except Exception as e:
        print(f"Error saving private key: {e}")
        raise e
    # Generate and save public key in PEM format

    try:
        public_key = private_key.public_key()
        with open(public_key_path, "wb") as f:
            f.write(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
        print(f"public key generated and saved in {public_key_path}")
    except Exception as e:
        print(f"Error saving public key: {e}")
        raise e

# Generate symmetric key (32 bytes) if it doesn't exist
try:
    if not os.path.exists(symmetric_key_path):
        symmetric_key = os.urandom(32)
        symmetric_key_b64 = base64.b64encode(symmetric_key)
        with open(symmetric_key_path, "wb") as f:
            f.write(symmetric_key_b64)
        print(f"symmetric key generated and saved in {symmetric_key_path}")
    else:
        print("symmetric key already exists")
except Exception as e:
    print(f"Error saving symmetric key: {e}")
    raise e

print("setting file permissions to 600")
# Set file permissions to 600 (read-write for owner only)
os.chmod(private_key_path, 0o600)
os.chmod(public_key_path, 0o600)
os.chmod(symmetric_key_path, 0o600)

print("keys generated successfully")
