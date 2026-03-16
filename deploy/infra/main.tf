locals {
  # Azure Container Registry names must be alphanumeric only.
  acr_name_sanitized = replace(var.acr_name, "-", "")

  # Azure Storage Account names must be lowercase alphanumeric only, 3-24 chars.
  storage_name_sanitized = lower(replace(var.storage_account_name, "-", ""))
}

# Reference the existing resource group — do not create or destroy it.
data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}
