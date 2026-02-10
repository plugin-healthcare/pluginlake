from fastapi import FastAPI, Depends, HTTPException, UploadFile, Header, Form
from cryptography.hazmat.primitives import serialization
from blobprox.config import logger, settings
from blobprox.utils import crypto
from blobprox.utils.helpers import string_to_bool
from blobprox.utils import blob
import json
import mimetypes
import io
from fastapi.responses import StreamingResponse

app = FastAPI(name="BlobProx")


def authenticate(
    x_decryption_key: str,
    x_salt: str,
    x_comparison_key: str,
) -> bool:
    try:
        encrypted_key = settings.API_KEY

        if not all([x_decryption_key, x_salt, x_comparison_key, encrypted_key]):
            raise HTTPException(status_code=400, detail="Missing authentication components")

        decrypted_key = crypto.decrypt_key(encrypted_key, x_decryption_key, x_salt)

        if decrypted_key == x_comparison_key:
            return True
        else:
            raise HTTPException(status_code=401, detail="Invalid key")

    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication failed") from e


def verify_authentication(
    x_decryption_key: str = Header(None, alias="x-decryption-key"),
    x_salt: str = Header(None, alias="x-salt"),
    x_comparison_key: str = Header(None, alias="x-comparison-key"),
) -> bool:
    """Dependency for authentication"""

    is_authenticated = authenticate(x_decryption_key, x_salt, x_comparison_key)
    logger.info(f"Authenticated: {is_authenticated}")

    if not is_authenticated:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@app.get("/key/public")
async def get_public_key(auth: bool = Depends(verify_authentication)) -> dict[str, str]:
    """Get the public key in PEM format"""
    try:
        public_key_pem = settings.rsa_public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")
        return {"public_key": public_key_pem}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving public key: {e}") from None


@app.post("/upload/{blob_container}/{blob_name:path}")
async def upload_blob(
    blob_container: str,
    blob_name: str,
    file: UploadFile,
    public_keys: str = Form(..., alias="public-keys"),
    overwrite: str = Form("False", alias="overwrite"),
    auth: bool = Depends(verify_authentication),
) -> dict[str, str | dict[str, str]]:
    """Symmetric encrypt file and upload to Azure Blob Storage. send symmetric keys encrypted with public keys."""
    file_data = await file.read()
    await file.close()
    overwrite = string_to_bool(overwrite)
    # encrypt data with symmetric key
    logger.info(f"Encrypting file: {blob_name}")

    try:
        public_keys_dict = json.loads(public_keys)
    except Exception as e:
        logger.error("Invalid public_keys format", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid public_keys format") from e

    try:
        file_data = crypto.symmetric_encrypt(file_data, settings.symmetric_key)
    except Exception as e:
        logger.error("encrypting failed")
        logger.debug(e, exc_info=True)
        raise HTTPException(status_code=500, detail="encrypting data failed") from None

    # encrypt symmetric key with RSA public keys
    logger.info("Encrypting symmetric key")
    try:
        keys = crypto.encrypt_keys(public_keys_dict, settings.symmetric_key)
    except Exception as e:
        logger.error("encrypting keys failed")
        logger.debug(e, exc_info=True)
        raise HTTPException(status_code=500, detail="encrypting failed") from None

    logger.info(f"Uploading file: {blob_name}")
    try:
        succes = blob.upload_blob(
            file_data, blob_container, blob_name, settings.blob_service_client, overwrite=overwrite
        )
        if not succes:
            raise FileExistsError
    except FileExistsError:
        logger.error(f"Blob already exists: {blob_name}")
        raise HTTPException(status_code=409, detail="Blob already exists") from None
    except Exception as e:
        logger.error("Upload failed")
        logger.debug(e, exc_info=True)
        raise HTTPException(status_code=500, detail="Upload failed") from None
    logger.info(f"File uploaded: {blob_name}")
    return {"filename": blob_name, "decryption_keys": keys}


@app.get("/download/{blob_container}/{blob_name:path}")
async def download_blob(
    blob_container: str,
    blob_name: str,
    decryption_key: str | None = Form(None, alias="decryption-key"),
    auth: bool = Depends(verify_authentication),
) -> StreamingResponse:
    """Download a file from Azure Blob Storage, decrypt it, and return the decrypted file."""

    # Decrypt the symmetric key using RSA private key
    logger.info("Decrypting symmetric key")
    try:
        symmetric_key = crypto.rsa_decrypt(decryption_key, settings.rsa_private_key)
    except Exception as e:
        logger.error("decrypting symmetric key failed")
        logger.debug(e, exc_info=True)
        raise HTTPException(status_code=500, detail="decrypting failed") from None

    # Download the blob data
    logger.info(f"Downloading file: {blob_name}")
    try:
        blob_io = blob.download_blob(blob_container, blob_name, settings.blob_service_client)
        blob_data = blob_io.read()
        blob_io.close()
    except Exception as e:
        logger.error("Download failed")
        logger.debug(e, exc_info=True)
        raise HTTPException(status_code=500, detail="Download failed") from None

    if blob_data is None:
        raise HTTPException(status_code=404, detail="Blob not found")

    # Decrypt the file data using the symmetric key
    logger.info("Decrypting file")
    logger.debug(f"Type of blob_data: {type(blob_data)}")
    logger.debug(f"Type of symmetric_key: {type(symmetric_key)}")
    try:
        decrypted_data = crypto.symmetric_decrypt(blob_data, symmetric_key)
    except Exception as e:
        logger.error("decrypting data failed")
        logger.debug(e, exc_info=True)
        raise HTTPException(status_code=500, detail="decrypting failed") from None

    # Determine a mimetype (optional, default to application/octet-stream)
    mime_type, _ = mimetypes.guess_type(blob_name)
    if mime_type is None:
        mime_type = "application/octet-stream"

    # Wrap the decrypted data in an IO-buffer
    file_stream = io.BytesIO(decrypted_data)

    logger.info(f"File decrypted: {blob_name}")
    # Return the content as a streaming response
    return StreamingResponse(
        file_stream, media_type=mime_type, headers={"Content-Disposition": f"attachment; filename={blob_name}"}
    )
