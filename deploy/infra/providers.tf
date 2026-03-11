terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}

  # Authentication — CLI (local dev):
  #   az login
  #   az account set --subscription "<id-or-name>"
  #
  # Authentication — service principal (CI/CD):
  #   set ARM_CLIENT_ID, ARM_CLIENT_SECRET, ARM_TENANT_ID, ARM_SUBSCRIPTION_ID

  # Required in azurerm ~> 4.0; can also be set via ARM_SUBSCRIPTION_ID env var.
  resource_provider_registrations = "none"
  subscription_id = var.subscription_id

}
