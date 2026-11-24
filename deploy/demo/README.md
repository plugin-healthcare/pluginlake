# Private demo on a tailnet

This runs the production stack with the ehds-demo project on the Scaleway VM from [deploy/infra/scaleway-demo](../infra/scaleway-demo/README.md).
Only devices in the tailnet can reach it, and nobody needs to install a certificate or own a domain.

## How it works

The station uses the tailnet's own domain (for example `example.ts.net`) as `[node].domain`.
Each subdomain the station serves (`auth`, `api`, `console`, `dagster`, `lineage` and `prometheus`) is a [Tailscale Service](https://tailscale.com/kb/1552/tailscale-services) with that name.
Tailscale gives every Service a trusted certificate and forwards HTTPS to Traefik on the VM's loopback interface, keeping the original Host header.
Traefik serves a certificate from a CA that exists only on the VM, which oauth2-proxy trusts for its internal call to the identity provider.
The images come from `ghcr.io/plugin-healthcare`, so the VM does not build anything.
The session cookie is valid for the whole tailnet domain, so a signed-in browser also sends it to other HTTPS hosts in the tailnet; that is acceptable only for a tailnet whose members are all trusted.

## Set up the tailnet once

In the Tailscale admin console, on the Services page, define the six Services `svc:auth`, `svc:api`, `svc:console`, `svc:dagster`, `svc:lineage` and `svc:prometheus` with endpoint `tcp:443`.
Add the following to the [tailnet policy](https://tailscale.com/kb/1337/policy-syntax), and remove or narrow any allow-all rule, because grants add up.

```json
"tagOwners": {"tag:pluginlake-demo": ["autogroup:admin"]},
"grants": [
  {"src": ["autogroup:member"], "dst": ["svc:auth", "svc:api", "svc:console", "svc:dagster", "svc:lineage", "svc:prometheus"], "ip": ["tcp:443"]},
  {"src": ["<maintainer login>"], "dst": ["tag:pluginlake-demo"], "ip": ["*"]}
],
"ssh": [
  {"action": "accept", "src": ["<maintainer login>"], "dst": ["tag:pluginlake-demo"], "users": ["demo-admin"]}
],
"autoApprovers": {
  "services": {
    "svc:auth": ["tag:pluginlake-demo"], "svc:api": ["tag:pluginlake-demo"], "svc:console": ["tag:pluginlake-demo"],
    "svc:dagster": ["tag:pluginlake-demo"], "svc:lineage": ["tag:pluginlake-demo"], "svc:prometheus": ["tag:pluginlake-demo"]
  }
}
```

Invite colleagues as members on the Users page; they install the Tailscale client and log in.
Members can only reach the Services on port 443, and only the maintainer can SSH into the VM.
On the VM, join the tailnet with `sudo tailscale up --advertise-tags=tag:pluginlake-demo --ssh` from the serial console (`scw instance server console <server id> zone=fr-par-1`), logging in as `demo-admin` with the console password.

## Run it

Copy `.env.example` to `.env` in this folder and fill in the SSH target, the tailnet domain and `DEMO_REF`.
Every `just demo-vm` command checks out `DEMO_REF` from GitHub in `~/pluginlake` on the VM, then runs [vm.sh](vm.sh) there and logs to `~/.local/state/pluginlake-demo` on the VM.
The VM therefore only runs what is pushed, and it needs nothing besides Docker and git: `pluginlake setup` runs from the ehds-demo image.

```bash
just demo-vm-power start
just demo-vm bootstrap   # once: joins the docker group and becomes Tailscale operator, asks for the sudo password
just demo-vm serve       # once: advertises the Tailscale Services
just demo-images-copy    # copies the images over SSH, so the VM needs no registry login
DEMO_PULL=0 just demo-vm up
just demo-vm data        # once: loads the Synthea test data
```

Open `https://console.<tailnet domain>` on a tailnet device.
The first administrator signs in with the password in `.pluginlake/secrets/zitadel_admin_password` on the VM and changes it when asked.
Afterwards, `just demo-vm ps`, `just demo-vm logs <service>` and `just demo-vm down` help, and `just demo-vm-power stop` stops the VM.
The VM also stops every evening, and after `just demo-vm-power start` the stack needs `just demo-vm up` again (with `DEMO_PULL=0` when the images were copied).

## Images

`just demo-images` builds the images for `linux/amd64` and tags them `demo` and with the commit; `just demo-images push` also pushes them.
Building needs a Docker login to `dhi.io`, and pushing needs a GitHub token with `write:packages`.
New GHCR packages are private, so either make the four packages public in their package settings and run `just demo-vm up`, or copy the images with `just demo-images-copy` and run `DEMO_PULL=0 just demo-vm up`.
Without the copy, the VM also needs `docker login dhi.io` for Postgres.
The ehds-demo image is built from a local `pluginlake-ehds-demo` checkout next to this repository, or from `DEMO_EHDS_DIR`.
When a dependency pin of that project cannot be fetched, put a wheel and an `overrides.txt` with `name @ file:///wheels/<wheel>` in `DEMO_WHEELS_DIR` to replace it.
