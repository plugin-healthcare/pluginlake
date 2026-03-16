# Infrastructure

This guide covers how to provision Azure resources for pluginlake using OpenTofu (or Terraform).
All configuration lives in `deploy/infra/`.

## Prerequisites

- [OpenTofu](https://opentofu.org/docs/intro/install/) >= 1.6.0 (or Terraform >= 1.6.0)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (`az`)
- An existing Azure resource group

Authenticate with Azure CLI before running any commands:

```bash
az login
az account set --subscription "<your-subscription-id>"
```

## File layout

```
deploy/infra/
├── main.tf            # Locals and data sources (resource group reference)
├── providers.tf       # Provider and version constraints
├── variables.tf       # All input variables with defaults
├── outputs.tf         # Output values after apply
├── acr.tf             # Azure Container Registry + RBAC
├── storage.tf         # Azure Storage Account + blob containers + RBAC
├── vm.tf              # Linux VM + networking (opt-in)
├── terraform.tfvars.example  # Template for your variable values
└── terraform.tfvars   # Your actual values (git-ignored)
```

## Getting started

### 1. Initialize the working directory

```bash
cd deploy/infra
tofu init
```

This downloads the `azurerm` provider and sets up the backend.

### 2. Create your variable file

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and fill in your subscription ID at minimum:

```hcl
subscription_id = "your-subscription-id-here"
```

!!! warning
    Never commit `terraform.tfvars` to version control. It contains sensitive values.

### 3. Preview changes

```bash
tofu plan
```

Review the output to see what resources will be created.

### 4. Apply

```bash
tofu apply
```

Confirm with `yes` when prompted.

## Resources

### Container Registry

Defined in `acr.tf`. Always created.

Provides a private Azure Container Registry with admin access disabled and anonymous pulls blocked.
All access is through Azure AD / service principal RBAC.

| Variable | Description | Default |
|----------|-------------|---------|
| `acr_name` | Registry name (hyphens stripped automatically) | `cr-plugin-demo-d` |
| `acr_sku` | SKU tier (`Basic`, `Standard`, `Premium`) | `Basic` |
| `acr_pull_principal_object_id` | Object ID for pull-only (AcrPull) access | `""` (skip) |
| `acr_push_principal_object_id` | Object ID for push+pull (AcrPush) access | `""` (skip) |

**Example: grant CI/CD push access and deployment pull access**

```hcl
acr_push_principal_object_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"  # CI pipeline SP
acr_pull_principal_object_id = "ffffffff-gggg-hhhh-iiii-jjjjjjjjjjjj"  # deployment runner SP
```

Find a principal's Object ID:

```bash
az ad sp show --id <APP_ID> --query id -o tsv
```

**Outputs:**

| Output | Description |
|--------|-------------|
| `acr_name` | Name of the registry |
| `acr_login_server` | Login server URL (use with `docker login`) |
| `acr_id` | Resource ID |

After apply, push images with:

```bash
az acr login --name $(tofu output -raw acr_name)
docker tag pluginlake $(tofu output -raw acr_login_server)/pluginlake:latest
docker push $(tofu output -raw acr_login_server)/pluginlake:latest
```

### Storage Account

Defined in `storage.tf`. Always created.

Provides a private Azure Blob Storage account with shared key access disabled, forcing Azure AD authentication only.
Includes soft delete (7 days) and enforces TLS 1.2+.

| Variable | Description | Default |
|----------|-------------|---------|
| `storage_account_name` | Account name (hyphens stripped automatically) | `st-plugin-demo-d` |
| `storage_account_tier` | Performance tier | `Standard` |
| `storage_replication_type` | Replication (`LRS`, `GRS`, etc.) | `LRS` |
| `storage_containers` | Blob containers to pre-create | `[]` |
| `service_principal_object_id` | Object ID for Storage Blob Data Contributor access | `""` (skip) |

**Example: create containers and grant SP access**

```hcl
storage_containers          = ["raw", "processed", "output"]
service_principal_object_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
```

**Outputs:**

| Output | Description |
|--------|-------------|
| `storage_account_name` | Name of the storage account |
| `storage_account_id` | Resource ID |
| `storage_primary_blob_endpoint` | Primary blob endpoint URL |

### Linux VM

Defined in `vm.tf`. Opt-in, disabled by default.

Provisions an Ubuntu 24.04 LTS virtual machine with SSH key authentication only (password auth disabled).
Includes a virtual network, subnet, network security group (SSH-only inbound), public IP, and network interface.

Enable it by setting `vm_enabled = true` in your `terraform.tfvars`.

| Variable | Description | Default |
|----------|-------------|---------|
| `vm_enabled` | Feature flag to create VM resources | `false` |
| `vm_name` | VM name | `vm-plugin-demo-d` |
| `vm_size` | Azure VM size | `Standard_B2s` |
| `vm_admin_username` | SSH admin username | `azureuser` |
| `vm_ssh_public_key` | SSH public key (required when enabled) | `""` |
| `vm_ssh_source_address_prefix` | CIDR allowed to SSH in | `*` |
| `vm_os_disk_type` | OS disk type | `Standard_LRS` |
| `vm_os_disk_size_gb` | OS disk size in GB | `30` |
| `vm_image` | Source image (publisher/offer/sku/version) | Ubuntu 24.04 LTS `24.04.202502210` |
| `vm_vnet_name` | Virtual network name | `vnet-plugin-demo-d` |
| `vm_vnet_address_space` | VNet address space | `10.0.0.0/16` |
| `vm_subnet_name` | Subnet name | `snet-default` |
| `vm_subnet_address_prefix` | Subnet address prefix | `10.0.1.0/24` |

**Example: enable the VM**

```hcl
vm_enabled                   = true
vm_ssh_public_key            = "ssh-rsa AAAA..."  # content of ~/.ssh/id_rsa.pub
vm_ssh_source_address_prefix = "203.0.113.10/32"  # restrict to your IP
```

To use a different Ubuntu image version, override `vm_image` in your `terraform.tfvars`.
List available versions first:

```bash
az vm image list --publisher Canonical --offer ubuntu-24_04-lts --sku server --all -o table
```

Then set the desired version:

```hcl
vm_image = {
  publisher = "Canonical"
  offer     = "ubuntu-24_04-lts"
  sku       = "server"
  version   = "24.04.202502210"
}
```

!!! tip
    Always set `vm_ssh_source_address_prefix` to your IP or office CIDR in production instead of the default `*`.

**Outputs:**

| Output | Description |
|--------|-------------|
| `vm_public_ip` | Public IP address |
| `vm_private_ip` | Private IP address |
| `vm_id` | Resource ID |
| `vm_ssh_command` | Ready-to-use SSH command |

After apply, connect to the VM:

```bash
tofu output -raw vm_ssh_command
# ssh azureuser@<public-ip>
```

## Common variables

These variables apply to all resources:

| Variable | Description | Default |
|----------|-------------|---------|
| `subscription_id` | Azure subscription ID (sensitive) | — |
| `resource_group_name` | Existing resource group name | `rg-plugin-demo-d` |
| `location` | Azure region | `westeurope` |
| `tags` | Tags applied to all resources | `project=pluginlake, environment=demo, managed_by=opentofu` |

## Common operations

### View current outputs

```bash
tofu output
```

### Destroy all resources

```bash
tofu destroy
```

### Destroy a specific resource

```bash
tofu destroy -target=azurerm_linux_virtual_machine.main
```

### Import an existing resource

```bash
tofu import azurerm_storage_account.main /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<name>
```

### CI/CD authentication

For non-interactive environments, authenticate via service principal environment variables instead of `az login`:

```bash
export ARM_CLIENT_ID="..."
export ARM_CLIENT_SECRET="..."
export ARM_TENANT_ID="..."
export ARM_SUBSCRIPTION_ID="..."
```
