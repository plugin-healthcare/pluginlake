# WebDAV Network Containers

This folder contains two Docker containers that can be used to test a WebDAV server and a WebDAV client communicating in a local network setup in a [Docker bridge network](https://docs.docker.com/network/network-tutorial-standalone/) fashion.

## apache-server
Apache 2 WebDAV server is used as the WebDAV server. The server is configured to serve files from the `/usr/local/apache2/htdocs/` directory over port 8081. The server config file can be found at `apache-server/httpd-cofnig.conf` and can be adjusted before build. It does not use any form of authentication and is only accessible through the docker bridge network.
The server serves files that are volume mounted to the `/usr/local/apache2/htdocs/` directory. It is run as user to protect the host system from any potential security vulnerabilities. To make the server able to read and write files from the mounted volume the `UID` and `PID` need to be set to the same as the user that has read/write access to the mounted volume. The server is run in a `httpd:2.4` container.

## webdav-client
The webdav client consists of a simple Python script that reads and writes files to the WebDAV server.  The client script reads and writes files from the `/usr/src/app/data/` directory. The client script is run in a `Python 3.10-slim` container.

## Requirements

- Docker: Make sure you have Docker engine installed on your machine.

## How to Use

1. Clone this repository to your local machine.

2. Navigate to the `containers/webdav-network` folder.

3. Edit path of `TEST_DATA_MOUNT` folder in `docker-compose.yaml` file. When in Windows, use the following format (note the forward slashes!): `C:/path/to/your/folder`. When in Linux, use the following format: `/path/to/your/folder`.

4. Build and run the WebDAV server and client containers and local bridge network by running the following command:

    ```bash
    docker-compose up -d --build
    ```

5. Check the log if client was succesfull in reading and writing the webdav server.

    ```bash
    docker-compose logs -f webdav-client
    ```

## Cleanup

To stop and remove the containers and network, run the following commands:

    ```bash
    docker-compose down
    ```
