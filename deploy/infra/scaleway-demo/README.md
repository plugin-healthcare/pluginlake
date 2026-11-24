# Private Scaleway demo VM

This OpenTofu root creates one Paris DEV1-L with a 50 GB boot disk and a public IPv4 address for outbound connections only.
The stateful security group has no inbound allow rules, so SSH, HTTP and HTTPS are reachable only over Tailscale.
A serverless job stops the VM every evening at 18:00 (Europe/Amsterdam) with an API key that may only stop servers.
Running the station on the VM is described in [the demo guide](../../demo/README.md).

## State

The state lives in a private, versioned Scaleway Object Storage bucket and is encrypted by OpenTofu with a passphrase.
Without the passphrase the state cannot be read, so keep it in the team password manager.
Copy `.env.example` to `.env` in this folder and fill it in; `.env` is gitignored.
`just demo-tofu` loads `.env`, takes the Object Storage credentials from your `scw` CLI profile and runs `tofu` here.

```bash
just demo-tofu init
just demo-tofu plan
```

The SSH key and console password hash only matter when the VM is created, because cloud-init runs once.
Use the values the VM was created with, otherwise `plan` shows a change to its user data.

## Provision once

Set `TF_VAR_ssh_public_key` to the administrator's public key and `TF_VAR_console_password_hash` to the output of `openssl passwd -6`, then run `just demo-tofu apply`.
Open the VM's [Scaleway serial console](https://www.scaleway.com/en/docs/instances/how-to/use-serial-console/) as `demo-admin`.
Run `sudo cloud-init status --wait`, then `sudo tailscale up --advertise-tags=tag:pluginlake-demo --ssh` and authenticate with its URL.
No Tailscale key goes into OpenTofu.

## Demo days

`just demo-vm-power start` starts the VM and `just demo-vm-power stop` stops it; after a start, `just demo-vm up` starts the stack ([deploy/demo](../../demo/README.md)).
Stopping keeps the disk and the Tailscale identity; disk and IP charges continue.
`tofu destroy` removes the VM and its demo data, so never use it as the daily stop command.
