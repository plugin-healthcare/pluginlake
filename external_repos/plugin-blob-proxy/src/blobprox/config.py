from pydantic_settings import BaseSettings
from pydantic import ValidationError
from dotenv import load_dotenv
from cryptography.hazmat.primitives.asymmetric import rsa
import os
import sys
from blobprox.utils import crypto
from blobprox.utils.helpers import read_json, string_to_bool
from functools import lru_cache
import logging
from azure.storage.blob import BlobServiceClient
from blobprox.utils import blob


logger = logging.getLogger("uvicorn.error")


def parse_validation_error(error: ValidationError) -> list[str]:
    """Parse a ValidationError to get missing fields."""
    missing_fields = []
    for er in error.errors():
        if er["type"] == "missing":
            missing_fields.append(er["loc"][0])
    return missing_fields


class Settings(BaseSettings):
    API_KEY: str
    STORAGE_URL: str
    rsa_private_key: rsa.RSAPrivateKey | None = None
    rsa_public_key: rsa.RSAPublicKey | None = None
    symmetric_key: bytes | None = None
    blob_service_client: BlobServiceClient | None = None
    prod: bool = True

    def __init__(self, **data):
        load_dotenv(override=True, verbose=True)

        super().__init__(**data)

        # if not KEY_VAULT_PATH in env set path to standard /.keys
        key_vault_path = os.getenv("KEY_VAULT_PATH", "/.keys")
        if not os.path.exists(key_vault_path):
            raise ValueError("Key vault path does not exist!")

        # Construct key paths using os.path.join
        ENCRYPTION_RSA_PRIVATE_KEY_PATH = os.path.join(key_vault_path, "rsa_private_key.pem")
        ENCRYPTION_RSA_PUBLIC_KEY_PATH = os.path.join(key_vault_path, "rsa_public_key.pem")
        SYM_CRYPT_KEY_PATH = os.path.join(key_vault_path, "symmetric_key.key")

        self.prod = string_to_bool(os.getenv("PROD", "true"))
        logger.info(f"running as prod: {self.prod}")

        try:
            self.rsa_private_key = crypto.read_rsa_private(ENCRYPTION_RSA_PRIVATE_KEY_PATH)
            self.rsa_public_key = crypto.read_rsa_public(ENCRYPTION_RSA_PUBLIC_KEY_PATH)
            self.symmetric_key = crypto.read_symmetric_key(SYM_CRYPT_KEY_PATH)
            logger.info("Keys loaded successfully.")
        except Exception as e:
            raise RuntimeError(f"Error loading keys: {e}") from e

        creds_path = os.getenv("STORAGE_CREDS", "/.secrets/creds.json")

        if not creds_path:
            raise ValueError("STORAGE_CREDS environment variable is not set")
        if not os.path.exists(creds_path):
            raise ValueError("STORAGE_CREDS file does not exist")
        creds = read_json(creds_path)
        service_client = blob.get_service_client(creds)
        self.blob_service_client = blob.get_blob_client(service_client, self.STORAGE_URL)
        logger.info("Blob service client created successfully.")


@lru_cache
def get_settings() -> Settings:
    """Get settings from environment variables or .env file."""
    try:
        settings = Settings()
        logger.info("Settings loaded successfully.")
        return settings
    except ValidationError as e:
        missing_fields = parse_validation_error(e)
        logger.error(f"Missing environment variables: {missing_fields}")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"blob storage credentials path not found or not in env: {e}")
        sys.exit(1)
    except blob.AzureBlobClientError as e:
        logger.error(f"Error creating BlobServiceClient: {e}")
        sys.exit(1)
    except blob.AzureServiceClientError as e:
        logger.error(f"Error creating ClientSecretCredential: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during configuration: {e}")
        sys.exit(1)


settings = get_settings()

if settings.prod:
    sys.tracebacklimit = 0
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.DEBUG)
# Suppress debug logs from the Azure SDK
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.storage.blob").setLevel(logging.WARNING)
logging.getLogger("azure.storage").setLevel(logging.WARNING)
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)
