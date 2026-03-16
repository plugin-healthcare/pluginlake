# ---------------------------------------------------------------------------
# Azure Linux Virtual Machine — SSH-only access, no public password auth
# ---------------------------------------------------------------------------

resource "azurerm_virtual_network" "main" {
  count               = var.vm_enabled ? 1 : 0
  name                = var.vm_vnet_name
  resource_group_name = data.azurerm_resource_group.main.name
  location            = var.location
  address_space       = [var.vm_vnet_address_space]

  tags = var.tags
}

resource "azurerm_subnet" "main" {
  count                = var.vm_enabled ? 1 : 0
  name                 = var.vm_subnet_name
  resource_group_name  = data.azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main[0].name
  address_prefixes     = [var.vm_subnet_address_prefix]
}

resource "azurerm_network_security_group" "main" {
  count               = var.vm_enabled ? 1 : 0
  name                = "${var.vm_name}-nsg"
  resource_group_name = data.azurerm_resource_group.main.name
  location            = var.location

  security_rule {
    name                       = "AllowSSH"
    priority                   = 1000
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.vm_ssh_source_address_prefix
    destination_address_prefix = "*"
  }

  tags = var.tags
}

resource "azurerm_subnet_network_security_group_association" "main" {
  count                     = var.vm_enabled ? 1 : 0
  subnet_id                 = azurerm_subnet.main[0].id
  network_security_group_id = azurerm_network_security_group.main[0].id
}

resource "azurerm_public_ip" "main" {
  count               = var.vm_enabled ? 1 : 0
  name                = "${var.vm_name}-pip"
  resource_group_name = data.azurerm_resource_group.main.name
  location            = var.location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = var.tags
}

resource "azurerm_network_interface" "main" {
  count               = var.vm_enabled ? 1 : 0
  name                = "${var.vm_name}-nic"
  resource_group_name = data.azurerm_resource_group.main.name
  location            = var.location

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main[0].id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.main[0].id
  }

  tags = var.tags
}

# User-assigned managed identity — grants the VM pull-only access to the Container Registry.
resource "azurerm_user_assigned_identity" "vm" {
  count               = var.vm_enabled ? 1 : 0
  name                = "${var.vm_name}-identity"
  resource_group_name = data.azurerm_resource_group.main.name
  location            = var.location

  tags = var.tags
}

resource "azurerm_role_assignment" "vm_acr_pull" {
  count                = var.vm_enabled ? 1 : 0
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.vm[0].principal_id
}

resource "azurerm_linux_virtual_machine" "main" {
  count               = var.vm_enabled ? 1 : 0
  name                = var.vm_name
  resource_group_name = data.azurerm_resource_group.main.name
  location            = var.location
  size                = var.vm_size

  admin_username                  = var.vm_admin_username
  disable_password_authentication = true
  custom_data                     = filebase64("${path.module}/cloud-init.yaml")

  lifecycle {
    precondition {
      condition     = var.vm_ssh_public_key != ""
      error_message = "vm_ssh_public_key must be set when vm_enabled = true."
    }
  }

  network_interface_ids = [azurerm_network_interface.main[0].id]

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm[0].id]
  }

  admin_ssh_key {
    username   = var.vm_admin_username
    public_key = var.vm_ssh_public_key
  }

  os_disk {
    name                 = "${var.vm_name}-osdisk"
    caching              = "ReadWrite"
    storage_account_type = var.vm_os_disk_type
    disk_size_gb         = var.vm_os_disk_size_gb
  }

  source_image_reference {
    publisher = var.vm_image.publisher
    offer     = var.vm_image.offer
    sku       = var.vm_image.sku
    version   = var.vm_image.version
  }

  tags = var.tags
}
