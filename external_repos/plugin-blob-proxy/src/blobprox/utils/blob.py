from io import BytesIO

from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient


class AzureServiceClientError(Exception):
    """Custom exception for Azure Service Client errors."""

    pass


class AzureBlobClientError(Exception):
    """Custom exception for Azure Blob Client errors."""

    pass


def get_service_client(creds: dict[str, str]) -> ClientSecretCredential:
    """Create and return a ClientSecretCredential object using the provided credentials."""

    missing = [key for key in ["tenantId", "clientId", "clientSecret"] if key not in creds or not creds[key]]
    if missing:
        raise ValueError(f"Credentials must contain non-empty values for: {', '.join(missing)}")
    try:
        return ClientSecretCredential(
            tenant_id=creds["tenantId"],
            client_id=creds["clientId"],
            client_secret=creds["clientSecret"],
        )
    except Exception as e:
        raise AzureServiceClientError("Error creating ClientSecretCredential") from e


def get_blob_client(credentials: ClientSecretCredential, url: str) -> BlobServiceClient:
    try:
        return BlobServiceClient(account_url=url, credential=credentials)
    except Exception as e:
        raise AzureBlobClientError("Error creating BlobServiceClient") from e


def upload_blob(
    data: bytes,
    container_name: str,
    blob_name: str,
    blob_service_client: BlobServiceClient,
    overwrite: bool = False,
) -> bool:
    """
    Upload a blob to Azure Blob Storage.

    Parameters:
    - data (bytes): The data to upload.
    - container_name (str): The name of the container.
    - blob_name (str): The name of the blob.
    - blob_service_client (BlobServiceClient): The BlobServiceClient instance.
    - overwrite (bool): Whether to overwrite the blob if it already exists.

    Returns:
    - bool: True if the blob was uploaded, False if it already exists and overwrite is False.
    """
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    if not overwrite and blob_client.exists():
        return False
    blob_client.upload_blob(data, overwrite=True)
    return True


def download_blob(container_name: str, blob_name: str, blob_service_client: BlobServiceClient) -> BytesIO | None:
    """
    Download a blob from Azure Blob Storage and return it as a BytesIO object.

    Parameters:
    - container_name (str): The name of the container.
    - blob_name (str): The name of the blob.
    - blob_service_client (BlobServiceClient): The BlobServiceClient instance.

    Returns:
    - BytesIO | None: The blob data as a BytesIO object, or None if the blob does not exist.
    """
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    if not blob_client.exists():
        return None
    blob_data = blob_client.download_blob().readall()
    return BytesIO(blob_data)


def list_blobs(container_name: str, blob_service_client: BlobServiceClient) -> list[str]:
    """
    List all blobs in a container.

    Parameters:
    - container_name (str): The name of the container.
    - blob_service_client (BlobServiceClient): The BlobServiceClient instance.

    Returns:
    - List[str]: A list of blob names in the container.
    """
    container_client = blob_service_client.get_container_client(container_name)
    blob_names = [blob.name for blob in container_client.list_blobs()]
    return blob_names


def delete_blob(container_name: str, blob_name: str, blob_service_client: BlobServiceClient) -> bool:
    """
    Delete a blob from Azure Blob Storage.

    Parameters:
    - container_name (str): The name of the container.
    - blob_name (str): The name of the blob.
    - blob_service_client (BlobServiceClient): The BlobServiceClient instance.

    Returns:
    - bool: True if the blob was deleted, False if it does not exist.
    """
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    if blob_client.exists():
        blob_client.delete_blob()
        return True
    return False


def list_containers(blob_service_client: BlobServiceClient) -> list[str]:
    """
    List all containers in the Azure Blob Storage account.

    Parameters:
    - blob_service_client (BlobServiceClient): The BlobServiceClient instance.

    Returns:
    - List[str]: A list of container names in the account.
    """
    container_names = [container.name for container in blob_service_client.list_containers()]
    return container_names
