output "resource_group_name" {
  description = "Name of the resource group."
  value       = data.azurerm_resource_group.main.name
}

# -- Container Registry --

output "acr_name" {
  description = "Name of the Container Registry."
  value       = azurerm_container_registry.main.name
}

output "acr_login_server" {
  description = "Login server URL for the Container Registry (use with `docker login`)."
  value       = azurerm_container_registry.main.login_server
}

output "acr_id" {
  description = "Resource ID of the Container Registry."
  value       = azurerm_container_registry.main.id
}

# -- Storage Account --

output "storage_account_name" {
  description = "Name of the Storage Account."
  value       = azurerm_storage_account.main.name
}

output "storage_account_id" {
  description = "Resource ID of the Storage Account."
  value       = azurerm_storage_account.main.id
}

output "storage_primary_blob_endpoint" {
  description = "Primary blob endpoint URL."
  value       = azurerm_storage_account.main.primary_blob_endpoint
}
