# pluginSHIRE: the home of happy data Hobbits who live & work in a composable data stack

> Every relevant health data point and the associated context are available to every authorized user within terms of use as defined by the data governance policies.

[PLUGIN](https://plugin.healthcare) is one the initiaves within the Health-RI ecosystems that aims to realize a federated data platform for secondary use of real-world data. The [joint health data architecure](https://health-ri.atlassian.net/wiki/spaces/HNG/pages/249074693/Joint+health+data+architecture+model) is taken as the starting point for the architecture of PLUGIN. The joint health data architecture model consists of 3 parts and a total of 26 components:

![Three parts and numbered components of the joint data architecture.](docs/images/health-ri-federated.png)

Within this reference architecture, the scope of PLUGIN covers key components and functionality as listed below.

| #  | Component                | Relevant PLUGIN         |
|:---|:-------------------------|:------------------------|
| 4  | EPD                      | Primary source of data  |
| 6  | Data interface           | pluginSHIRE data engineering framework that for composable, Python-based data processing pipelines |
| 7  | Persistent data platform | Hospital 'datastation', where data is persisted using a serverless lakehouse architecture and FHIR as a common data model |
| 8  | Metadata                 | part of pluginSHIRE, implemented using Apache Iceberg |
| 9  | API                      | part of pluginSHIRE, standardized APIs from underlying open source components are exposed |
| 10 | Versioning               | part of pluginSHIRE, implemented usign Apache Iceberg |
| 15 | Identification           | ... |
| 16 | Metadata templates       | ... |
| 17 | Mapping                  | Transformation scripts, written pre-defined coding standards and naming conventions as part of the data pipeline. Use of SQL-on-FHIR standard for creating flattened, tabular views of nested FHIR re |
| 18 | (De-)pseudonymization    | ... |
| 22 | Portal                   | ... |
| 23 | Metadata catalogue       | Implement using Apache Iceberg |
| 24 | Research dataset         | ... |
| 25 | Federated analyis        | pluginML federated learning framework, based on vantage6 and flower |
| 26 | Approval                 | ... |

For more details on the high-level functional requirements, please refer to the Agreements on the National Health Data Infrastructure for Research, Policy and Innovation ([v1.0](https://health-ri.atlassian.net/wiki/spaces/HNG/pages/249073646/Agreements+on+the+National+Health+Data+Infrastructure+for+Research+Policy+and+Innovation)). In the following we describe:

- Describe the **rationale** and **design** of the PLUGIN architecture
- Provide a **implementation details** of the architecture
- Provide **guides** how to work and develope data pipelines within this architecture

# Working with this repository

## Using devcontainers optimized for data science & -engineering

The [VS Code Dev Containers extension](https://code.visualstudio.com/docs/devcontainers/containers) lets you use a container as a full-featured development environment. It allows you to open any folder inside (or mounted into) a container and take advantage of VS Code full feature set. It is an alternative to using Python virtual environments, with the benefit that you can customize the whole runtime. This is particularly useful when dealing with alternative chipsets, such as ARM64/Apple M-series, and managing dependencies for using GPUs.

We use the pre-configured [Data Science Devcontainers](https://github.com/b-data/data-science-devcontainers), which have already taken care of optimizing the whole setup of the devcontainer. To start using them, do the following:

- Install and run Docker
- Note that data is persisted in the container
  - When using an unmodified devcontainer.json: work in `/home/vscode` which is the `home` directory of user `vscode`
  - Python packages are installed to the home directory by default. This is due to env variable `PIP_USER=1`
  - Note that the directory `/workspaces` is also persisted

### Making changes to the devcontainer

You can change the setup of the devcontainer in the following layers:

- Change (one of) the `Dockerfile`(s): do this is you need to optimize the basic container runtime
- Change `devcontainer.json`: use this to
  - Specify which VS Code extensions you want
  - Specify which apt-packages you need (useful for experimenting without changing the Dockerfile), for example adding `default-jdk` to be able to run pyspark
- Change `/workspaces/rusty-python/.devcontainer/scripts/usr/local/bin/onCreateCommand.sh`: add any other stuff, such as customizing the shell or installing a `requirements.txt`

## Rusty Python for data science & AI

We love the Rustification of Python because it improves the development with tools such as
-   [Ruff](https://docs.astral.sh/ruff/) for linting and code formatting
-   [uv](https://github.com/astral-sh/uv) as a drop-in replacement for `pip`
-   [rye](https://github.com/astral-sh/rye) as a comprehensive project and package management solution for Python
-   [pixi](https://prefix.dev/) as fast software package manager built on top of the existing conda ecosystem

For data science & AI, we enjoy significant performance gains with
- [polars](https://pola.rs/) to handle DataFrames in the new era, and writing plugins in Rust is [not that hard](https://marcogorelli.github.io/polars-plugins-tutorial/)
- [pydantic](https://docs.pydantic.dev/latest/) for data validation, on top of which we also use
  - [pandera](https://pandera.readthedocs.io/en/stable/) for flexible and expressive API validation on dataframe-like objects
  - [fhir.resources](fhir.resrouces) for validating FHIR Resources
- [tokenizers](https://github.com/huggingface/tokenizers) by Huggingface, that provides an implementation of today's most used tokenizers, with a focus on performance and versatility
- [VegaFusion](https://vegafusion.io/index.html) provides serverside scaling for the Vega visualization library, including the Altair Python interface to Vega-Lite
- [Robyn](https://robyn.tech/), a web framework that can be used to build async APIs

## containers currently living in the pluginSHIRE

### apache-server

This container can be used to host a apache 2 server. The server is configured to serve local host content that is volume mounted to the server through http://localhost:8081. It currently accepts webdav and http requests.
**Usage**
- adjust the path to volume mount in the docker-compose.yml file (:warning: Don't change the docker container file folder just the local path)
- `docker compose up -d --build`
- access the server through `http://localhost:8081`
- test server with`test_webdav_ffspec.ipynb`

### fsspec-webdav-nb

This container contains code to test the fsspec webdav apache server implementation. It starts a jupyter notebook server that can talk to the apache-server container. The notebook is used to test the webdav implementation of fsspec through docker container.

**Usage**
- `docker build -t fsspec-webdav-nb .`
- `docker run --network="host" -it fsspec-webdav-nb:latest`

### v6-http-test
This container contains code for a vantage6 algorithm that can be used to test the local apache webdav server.

**Usage**
- login to `drplugindhdprd.azurecr.io` with `docker login drplugindhdprd.azurecr.io` + credentials
- `docker build -t v6-http-test .`
- `docker tag v6-http-test drplugindhdprd.azurecr.io/v6-http-test`
- `docker push drplugindhdprd.azurecr.io/v6-http-test`
- run test notebook `test_http_folders.ipynb`
