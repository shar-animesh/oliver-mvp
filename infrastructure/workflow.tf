data "azurerm_managed_api" "office365" {
  name     = "office365"
  location = azurerm_resource_group.oliver.location
}

resource "azurerm_api_connection" "office365" {
  name                = "office365-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.oliver.name
  managed_api_id      = data.azurerm_managed_api.office365.id
  display_name        = "Oliver Office 365 connection (${var.environment})"

  lifecycle {
    ignore_changes = [parameter_values]
  }
}

locals {
  oliver_api_url = "https://${azurerm_container_app.oliver.ingress[0].fqdn}/api/v1/email/respond"

  workflow_definition = jsondecode(
    templatefile(
      "${path.module}/workflow/oliver-email-workflow.json.tftpl",
      {
        mailbox_address      = var.mailbox_address
        oliver_api_url       = local.oliver_api_url
        oliver_api_base_url  = "https://${azurerm_container_app.oliver.ingress[0].fqdn}/api/v1/email"
        oliver_api_audience  = one(azuread_application.oliver_api.identifier_uris)
        workflow_identity_id = azurerm_user_assigned_identity.email_workflow.id
      },
    )
  )

  office365_connection = {
    office365 = {
      connectionId   = azurerm_api_connection.office365.id
      connectionName = azurerm_api_connection.office365.name
      id             = data.azurerm_managed_api.office365.id
    }
  }
}

resource "azapi_resource" "email_workflow" {
  type      = "Microsoft.Logic/workflows@2019-05-01"
  name      = "logic-${local.name_prefix}-email"
  parent_id = azurerm_resource_group.oliver.id
  location  = azurerm_resource_group.oliver.location
  tags      = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.email_workflow.id]
  }

  body = {
    properties = {
      state      = "Enabled"
      definition = local.workflow_definition
      parameters = {
        "$connections" = {
          value = local.office365_connection
        }
      }
    }
  }

  response_export_values = ["properties.accessEndpoint"]
}

resource "azurerm_user_assigned_identity" "email_workflow" {
  name                = "id-${local.name_prefix}-email-workflow"
  resource_group_name = azurerm_resource_group.oliver.name
  location            = azurerm_resource_group.oliver.location
  tags                = local.common_tags
}
