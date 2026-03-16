variable "subscription_id" {
  description = "Azure subscription ID. Can also be set via the ARM_SUBSCRIPTION_ID environment variable."
  type        = string
  sensitive   = true
}

variable "resource_group_name" {
  description = "Name of the existing Azure resource group."
  type        = string
  default     = "rg-plugin-demo-d"
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "westeurope"
}

variable "acr_name" {
  description = "Desired name for the Container Registry. Hyphens are stripped automatically (Azure requirement: alphanumeric only, 5-50 chars)."
  type        = string
  default     = "cr-plugin-demo-d"
}

variable "acr_sku" {
  description = "SKU tier for the Container Registry."
  type        = string
  default     = "Basic"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "ACR SKU must be Basic, Standard, or Premium."
  }
}

variable "storage_account_name" {
  description = "Desired name for the Storage Account. Hyphens are stripped automatically (Azure requirement: lowercase alphanumeric only, 3-24 chars)."
  type        = string
  default     = "st-plugin-demo-d"
}

variable "storage_account_tier" {
  description = "Performance tier for the Storage Account."
  type        = string
  default     = "Standard"
}

variable "storage_replication_type" {
  description = "Replication type for the Storage Account."
  type        = string
  default     = "LRS"
}

variable "storage_containers" {
  description = "List of blob containers to create in the Storage Account."
  type        = list(string)
  default     = []
}

variable "acr_pull_principal_object_id" {
  description = "Object ID of the principal (SP, managed identity, group) that gets AcrPull (read-only) access. Leave empty to skip."
  type        = string
  default     = ""
}

variable "acr_push_principal_object_id" {
  description = "Object ID of the principal (SP, managed identity, group) that gets AcrPush (push + pull) access. Leave empty to skip."
  type        = string
  default     = ""
}

variable "service_principal_object_id" {
  description = "Object ID of the service principal that will be granted access to Blob Storage. Leave empty to skip role assignments."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default = {
    project     = "pluginlake"
    environment = "demo"
    managed_by  = "opentofu"
  }
}

# ---------------------------------------------------------------------------
# Linux VM
# ---------------------------------------------------------------------------

variable "vm_enabled" {
  description = "Whether to create the Linux VM and its networking resources."
  type        = bool
  default     = false
}

variable "vm_name" {
  description = "Name of the Linux virtual machine."
  type        = string
  default     = "vm-plugin-demo-d"
}

variable "vm_size" {
  description = "Azure VM size (SKU)."
  type        = string
  default     = "Standard_B2s"
}

variable "vm_admin_username" {
  description = "Admin username for the VM. Password auth is disabled; use SSH keys."
  type        = string
  default     = "azureuser"
}

variable "vm_ssh_public_key" {
  description = "SSH public key for VM access. Required when vm_enabled = true."
  type        = string
  default     = ""
}

variable "vm_ssh_source_address_prefix" {
  description = "CIDR or IP allowed to SSH into the VM. Use a restrictive value in production."
  type        = string
  default     = "*"
}

variable "vm_os_disk_type" {
  description = "Managed disk type for the OS disk."
  type        = string
  default     = "Standard_LRS"

  validation {
    condition     = contains(["Standard_LRS", "StandardSSD_LRS", "Premium_LRS"], var.vm_os_disk_type)
    error_message = "OS disk type must be Standard_LRS, StandardSSD_LRS, or Premium_LRS."
  }
}

variable "vm_os_disk_size_gb" {
  description = "Size of the OS disk in GB."
  type        = number
  default     = 30
}

variable "vm_image" {
  description = "Source image reference for the VM."
  type = object({
    publisher = string
    offer     = string
    sku       = string
    version   = string
  })
  default = {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

variable "vm_vnet_name" {
  description = "Name of the virtual network for the VM."
  type        = string
  default     = "vnet-plugin-demo-d"
}

variable "vm_vnet_address_space" {
  description = "Address space for the virtual network."
  type        = string
  default     = "10.0.0.0/16"
}

variable "vm_subnet_name" {
  description = "Name of the subnet for the VM."
  type        = string
  default     = "snet-default"
}

variable "vm_subnet_address_prefix" {
  description = "Address prefix for the VM subnet."
  type        = string
  default     = "10.0.1.0/24"
}
