# Deployment

This folder holds two kinds of deployment files.
The platform part is maintained together with pluginlake and is what every node runs.
The reference deployments are examples of how one organisation runs pluginlake on its own infrastructure, and they are not part of the core platform.

## Platform

These files define a pluginlake node and change together with the code.

- [compose](compose/) contains the Docker Compose stacks: `docker-compose.yaml` for a node, `docker-compose.dev.yaml` for development and `docker-compose.smoke.yaml` for the smoke test.
- [docker](docker/) contains the Dockerfiles of the pluginlake images.
- [monitoring](monitoring/) contains the Prometheus configuration that the node stack mounts.

`just setup`, `just up` and `just down` use these files, as described in the [documentation](../docs/).

## Reference deployments

These deployments run the platform somewhere specific.
They depend on a provider, a network setup or a demo project, and they are maintained on a best-effort basis.

- [infra](infra/) creates an Azure container registry and storage account with OpenTofu.
- [infra/scaleway-demo](infra/scaleway-demo/README.md) creates the Scaleway VM for the private demo, with its OpenTofu state encrypted in Object Storage.
- [demo](demo/README.md) runs the platform with the ehds-demo project on that VM, reachable only through a Tailscale tailnet.

A reference deployment uses the platform files as they are and adds its own files next to them, such as a compose override, so the platform stays free of provider-specific choices.
