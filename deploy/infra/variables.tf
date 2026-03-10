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

variable "service_principal_object_id" {
  description = "Object ID of the service principal that will be granted access to ACR and Blob Storage. Leave empty to skip role assignments."
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
