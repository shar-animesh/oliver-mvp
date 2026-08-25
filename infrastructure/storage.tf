resource "azurerm_storage_account" "oliver" {
  name                          = "st${substr(local.unique_name, 0, 22)}"
  resource_group_name           = azurerm_resource_group.oliver.name
  location                      = azurerm_resource_group.oliver.location
  account_tier                  = "Standard"
  account_replication_type      = var.environment == "prod" ? "ZRS" : "LRS"
  min_tls_version               = "TLS1_2"
  public_network_access_enabled = true
  shared_access_key_enabled     = false
  tags                          = local.common_tags

  network_rules {
    default_action             = "Deny"
    bypass                     = ["AzureServices"]
    virtual_network_subnet_ids = [azurerm_subnet.container_apps.id]
  }

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = var.environment == "prod" ? 30 : 7
    }

    container_delete_retention_policy {
      days = var.environment == "prod" ? 30 : 7
    }
  }
}

resource "azurerm_storage_container" "attachments" {
  name                  = "attachments"
  storage_account_id    = azurerm_storage_account.oliver.id
  container_access_type = "private"
}

resource "azurerm_role_assignment" "workloads_attachment_contributor" {
  scope                = azurerm_storage_account.oliver.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.workloads.principal_id
}
