# plugin-blob-proxy

Azure Blob Storage proxy for the pluginML package. This service provides secure communication with Azure Blob Storage by encrypting files before upload and decrypting them on download.

## Overview

The proxy offers fastAPI endpoints to upload and download files as blob to azure blob storage. Files are encrypted with a symmetric key (using Fernet from the [cryptography](https://cryptography.io) library), and the symmetric key itself is encrypted with RSA public keys provided by the client. This design ensures only authorized clients (in possession of the corresponding RSA private key) can decrypt the symmetric key and subsequently the file.
Each blob proxy container has it's own set of symmetric, and RSA public and private key.

### Authentication

The proxy uses a custom authentication mechanism to ensure secure communication between the client and the server. This is the only encryption that is shared between all blob proxies within a collaboration. These keys can be generated once and stored on the host machines of the blob proxies. The keys are used to authenticate the client.

The client must provide three custom headers with each request:

- **`x-decryption-key`:**
  A unique key used to decrypt the symmetric key. This key is stored in the Azure Blob Storage account and is used to encrypt the symmetric key.
- **`x-salt`:**
  A unique salt value used to generate the symmetric key. This salt is stored in the Azure Blob Storage account and is used to encrypt the symmetric key.
- **`x-comparison-key`:**
  A unique key used to compare the decryption key with the key stored in the Azure Blob Storage account.

The server verifies these headers in the [verify_authentication](src/blobprox/main.py) function before processing the request.

> :warning:

### Key Generation

The proxy uses RSA public and private keys to encrypt and decrypt symmetric keys. The keys are generated using the provided key generation script. The script generates a pair of RSA keys (2048 bits) and a symmetric key (256 bits) and stores them in the `.keys` directory. The RSA private key is stored in the `.keys` directory, and the public key is exposed via the `/key/public` endpoint.

The symmetric key is generated using the Fernet library from the [cryptography](https://cryptography.io) package. The key is stored in Base64-encoded form in the `.keys` directory.

### Azure Blob Storage

The proxy interacts with Azure Blob Storage using the [Azure SDK for Python](https://github.com/azure/azure-sdk-for-python/). By volume mounting the Azure credentials file, locally stored on the host machine, the proxy can authenticate with Azure Blob Storage and access the specified containers. Based on the access permissions provided to the azure service principal, the proxy can read and/or write files to the specified containers. The proxy itself does not store any information on the blob storage storage container structure or the blob storage permissions of the user.

### File encryption

The proxy uses a combination of symmetric and asymmetric encryption to secure files. The files itself are encrypted with a symmetric key, optimized for large files. The symmetric key is then encrypted with the public RSA key of the receiver. This means that to upload a blob you need to provide one or multiple public keys from the blob proxies that will be downloading the file. The encrypted symmetric key is returned in the response of the upload endpoint and can be used to decrypt the file.

An example of the response of the upload endpoint:
```json
{
  "file_name": "blob_name.parquet",
  "keys": {
    "blob_proxy_1": "encrypted_symmetric_key",
    "blob_proxy_2": "encrypted_symmetric_key"
  }
}
```

> :bulb: **Note:**
> RSA encrypt always requires the public key from the recipient that will decrypt the message.
> The public key can be retrieved through the endpoint and is always send in the request to upload a file.


### FastAPI endpoints

For each endpoint, the client must provide the custom headers `x-decryption-key`, `x-salt`, and `x-comparison-key` for authentication as follows:

```
headers = {
    "x-decryption-key": "<your_decryption_key>",
    "x-salt": "<your_salt>",
    "x-comparison-key": "<your_comparison_key>"
}
```

- **GET `/key/public`:**
  Returns the RSA public key in PEM format. Use this endpoint to get the public key needed to encrypt symmetric keys.

- **POST `/upload/{blob_container}/{blob_name:path}`:**
  Encrypts and uploads a file to Azure Blob Storage. The file is encrypted with the symmetric key, and the symmetric key is encrypted with provided RSA public keys.
  **Parameters:**
  - `public-keys` (Form): JSON mapping of key identifiers to RSA public keys
  - `overwrite` (Form): Indicates whether to overwrite an existing blob. Defaults to `false`.
  - `file` (UploadFile): The file to upload.

  **Example request:**
  ```python
  import requests
  data = {
      "overwrite": "true"
  }
  files = {
      "file": open("/path/to/local/file.txt", "rb"),
      "public-keys": open("/path/to/public_keys.json", "rb")
  }
  response = requests.post("http://localhost:8082/upload/mycontainer/myfile.txt", headers=headers, data=data, files=files)
  print(response.json())
  ```

- **GET `/download/{blob_container}/{blob_name:path}`:**
  Downloads an encrypted file, decrypts the symmetric key using the RSA private key, and then decrypts the file before streaming it back to the client.
  **Parameters:**
  - `decryption_key` (Form): The decryption key used to decrypt the symmetric key.

  **Example request:**
  ```python
  import requests
  import polars as pl
  response = requests.get(f"{base_url}/download/{blobcontainer}/{blobname}", headers=headers, data=data)

  buffer = BytesIO(response.content)
  df = pl.read_parquet(buffer)
  ```

## Installation

### Prerequisites

- Python 3.12.x
- Docker engine (to run via Docker Compose)
- An Azure Blob Storage account and corresponding credentials to read and/or write access to storage containers

### Setup development environment

1. **Clone the Repository:**

   ```sh
   git clone https://github.com/DutchHospitalData/plugin-blob-proxy.git
   cd plugin-blob-proxy
   ```

2. **Install Python 3.12:**

   ```sh
    uv python install 3.12
    ```

3. **Install the required dependencies + dev dependencies:**

   ```sh
  uv sync
   ```

> can also be installed using pip by running `pip install -e .[dev]`

## Configuration

In both local and docker-compose setups, the proxy requires authentication credentials to be generated. These credentials are only created once and can be shared between all proxies in a collaboration. The proxy only stores the encrypted key and the client must provide the decryption key and salt to authenticate with the proxy.

### local development
4. **Set .env file with the following variables:**
  - `API_KEY`: The API key for authentication this key is the same for all proxies.

    ```sh
    API_KEY=<your_api_key>
    STORAGE_URL=<your_storage_url>
    KEY_VAULT_PATH=<path_to_key_vault>
    STORAGE_CREDS=<path_to_azure_creds>
   ```

   > :bulb: **Note:** The .env file is only required for local development. In production, you only need to set some of these environment variables in the docker compose.


### Setup as docker container

```sh
docker pull drplugindhdprd.azurecr.io/plugin/blob-proxy-keygen
docker pull drplugindhdprd.azurecr.io/plugin/blob-proxy-server
```

## Usage

Before usage, if not done before, authentication keys need to be generated. This can be done by running the keygen container.

```sh

### Run Locally

It is possible to run the proxy locally.

1. **Generate proxy server keys if not created before**

   ```sh
   python src/blobprox/utils/generate_keys.py -p <path_to_key_dir>
   ```


2. **Run the server service:**
   ```sh
   uvicorn src.blobprox.main:app --host 0.0.0.0 --port 8082
   ```
### Run via Docker Compose

1. **Clone the Repository:**

   ```sh
   git clone https://github.com/DutchHospitalData/plugin-blob-proxy.git
   cd plugin-blob-proxy
   ```

3. a. **build the docker images:**

   ```sh
   make docker-build-keygen
   make docker-build-server
   ```

   b. or pull the images from the container registry (credentials required):

   ```sh
   docker login drplugindhd.azurecr.io
   docker pull drplugindhd.azurecr.io/plugin/blob-proxy-keygen
   docker pull dutchhospitaldata/plugin/blob-proxy-server

2. **Adjust docker-compose**

  Replace the following placeholders in the `docker-compose.yaml` file:
  - `<registry-url>` *remove the registry url or adjust accordingly if containers are locally built*
  - `<uid>` *Use the uid of a linux user on the host machine to avoid volume permission issues*
  - `<gid>` *Use the gid of a linux user on the host machine to avoid volume permission issues*
  - `<local-key-dir>` *path to the directory where the keys are stored*
  - `<api-key>` encrypted key for api server authentication
  - `<storage-url>`
  - `<creds-path>`
The `docker-compose.yaml` file defines two services:

- **keygen:** Generates the necessary RSA and symmetric keys.
  - **Volumes:** Mounts the `.keys` directory to `/keys` inside the container.

- **blobprox:** Runs the main application.
  - **Ports:** Maps port `8082` on the host to port `8082` in the container.
  - **Volumes:**
    - Mounts the `.keys` directory as read-only.
    - Mounts the Azure credentials file as read-only.
  - **Environment Variables:**
    - `API_KEY`: The API key for authentication.
    - `STORAGE_URL`: The URL of the Azure Blob Storage account.
  - **Depends on:** The `keygen` service to ensure keys are generated before starting.

### Usage

Once the application is running, you can access the endpoints using any HTTP client. Below are examples using Python's `requests` library.

- **GET `/key/public`:**
  Retrieve the RSA public key to encrypt symmetric keys.

  ```python
  import requests

  headers = {
      "x-decryption-key": "<your_decryption_key>",
      "x-salt": "<your_salt>",
      "x-comparison-key": "<your_comparison_key>"
  }

  response = requests.get("http://localhost:8082/key/public", headers=headers)
  print(response.json())
  ```

- **POST `/upload/{blob_container}/{blob_name:path}`:**
  Upload and encrypt a file to Azure Blob Storage.

  ```python
  import requests

  headers = {
      "x-decryption-key": "<your_decryption_key>",
      "x-salt": "<your_salt>",
      "x-comparison-key": "<your_comparison_key>"
  }

  files = {
      "file": open("/path/to/local/file.txt", "rb"),
      "public-keys": open("/path/to/public_keys.json", "rb")
  }

  data = {
      "overwrite": "true"
  }

  response = requests.post("http://localhost:8082/upload/mycontainer/myfile.txt", headers=headers, files=files, data=data)
  print(response.json())
  ```

- **GET `/download/{blob_container}/{blob_name:path}`:**
  Download and decrypt a file from Azure Blob Storage.

  ```python
  import requests

  headers = {
      "x-decryption-key": "<your_decryption_key>",
      "x-salt": "<your_salt>",
      "x-comparison-key": "<your_comparison_key>"
  }

  response = requests.get("http://localhost:8082/download/mycontainer/myfile.txt", headers=headers)

  with open("/path/to/save/file.txt", "wb") as f:
      f.write(response.content)
  ```

Ensure you replace placeholders like `<your_decryption_key>`, `<your_salt>`, and `<your_comparison_key>` with actual values.
