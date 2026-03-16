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

# -- Linux VM --

output "vm_public_ip" {
  description = "Public IP address of the Linux VM."
  value       = var.vm_enabled ? azurerm_public_ip.main[0].ip_address : null
}

output "vm_private_ip" {
  description = "Private IP address of the Linux VM."
  value       = var.vm_enabled ? azurerm_network_interface.main[0].private_ip_address : null
}

output "vm_id" {
  description = "Resource ID of the Linux VM."
  value       = var.vm_enabled ? azurerm_linux_virtual_machine.main[0].id : null
}

output "vm_ssh_command" {
  description = "SSH command to connect to the VM."
  value       = var.vm_enabled ? "ssh ${var.vm_admin_username}@${azurerm_public_ip.main[0].ip_address}" : null
}

output "vm_identity_client_id" {
  description = "Client ID of the VM managed identity (use with `az acr login --identity` or Docker credential helpers)."
  value       = var.vm_enabled ? azurerm_user_assigned_identity.vm[0].client_id : null
}

output "vm_identity_principal_id" {
  description = "Principal ID of the VM managed identity."
  value       = var.vm_enabled ? azurerm_user_assigned_identity.vm[0].principal_id : null
}
