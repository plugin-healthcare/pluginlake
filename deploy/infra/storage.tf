# ---------------------------------------------------------------------------
# Azure Blob Storage — private, RBAC-only access
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "main" {
  name                = local.storage_name_sanitized
  resource_group_name = data.azurerm_resource_group.main.name
  location            = var.location

  account_tier             = var.storage_account_tier
  account_replication_type = var.storage_replication_type
  account_kind             = "StorageV2"

  # Block all anonymous/public blob access at the account level.
  allow_nested_items_to_be_public = false

  # Disable shared key (account key) access — force Azure AD auth only.
  shared_access_key_enabled = false

  # Network is reachable but every request must be authenticated.
  public_network_access_enabled = true

  # Enforce HTTPS only.
  https_traffic_only_enabled = true

  # Use Azure AD authorization by default in the portal.
  default_to_oauth_authentication = true

  # Require minimum TLS 1.2.
  min_tls_version = "TLS1_2"

  # Enable blob soft delete for recovery (7 days).
  blob_properties {
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }

  tags = var.tags
}

# Create blob containers if specified.
resource "azurerm_storage_container" "containers" {
  for_each              = toset(var.storage_containers)
  name                  = each.value
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

# Grant the service principal read/write access to blobs.
resource "azurerm_role_assignment" "storage_blob_contributor" {
  count                = var.service_principal_object_id != "" ? 1 : 0
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.service_principal_object_id
}
