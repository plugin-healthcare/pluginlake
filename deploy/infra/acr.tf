# ---------------------------------------------------------------------------
# Azure Container Registry — private, RBAC-only access
# ---------------------------------------------------------------------------

resource "azurerm_container_registry" "main" {
  name                = local.acr_name_sanitized
  resource_group_name = data.azurerm_resource_group.main.name
  location            = var.location
  sku                 = var.acr_sku

  # Disable the built-in admin account — all access goes through Azure AD / SP.
  admin_enabled = false

  # Disable anonymous (unauthenticated) image pulls.
  anonymous_pull_enabled = false

  # Network is reachable but every request must be authenticated.
  public_network_access_enabled = true

  tags = var.tags
}

# Pull-only access (e.g. deployment runners, read-only consumers).
resource "azurerm_role_assignment" "acr_pull" {
  count                = var.acr_pull_principal_object_id != "" ? 1 : 0
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = var.acr_pull_principal_object_id
}

# Push + pull access (e.g. CI/CD pipelines that build and push images).
resource "azurerm_role_assignment" "acr_push" {
  count                = var.acr_push_principal_object_id != "" ? 1 : 0
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPush"
  principal_id         = var.acr_push_principal_object_id
}
