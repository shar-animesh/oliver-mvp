locals {
  oliver_app_roles = {
    "Oliver.Admin.Read" = {
      display_name = "Oliver administrator read"
      description  = "View canonical initiatives, evidence, assessments, delivery state, and audit history."
      member_types = ["User"]
    }
    "Oliver.Assessment.Test" = {
      display_name = "Oliver assessment operator"
      description  = "Run governed test assessments and portfolio insight generation."
      member_types = ["User"]
    }
    "Oliver.Lifecycle.Approve" = {
      display_name = "Oliver lifecycle approver"
      description  = "Approve, reject, hold, or resume governed lifecycle decisions."
      member_types = ["User"]
    }
    "Oliver.Scout.Review" = {
      display_name = "Oliver Scout reviewer"
      description  = "Review, promote, or dismiss Scout candidates."
      member_types = ["User"]
    }
    "Oliver.Platform.Admin" = {
      display_name = "Oliver platform administrator"
      description  = "Perform all Oliver administrative and governance actions."
      member_types = ["User"]
    }
    "Oliver.Service.Email" = {
      display_name = "Oliver email workload"
      description  = "Submit inbound email and report delivery outcomes."
      member_types = ["Application"]
    }
    "Oliver.Service.Scheduler" = {
      display_name = "Oliver scheduler workload"
      description  = "Run deterministic cadence and lifecycle scheduling operations."
      member_types = ["Application"]
    }
    "Oliver.Service.Scout" = {
      display_name = "Oliver Scout connector workload"
      description  = "Submit records from explicitly approved Scout sources."
      member_types = ["Application"]
    }
    "Oliver.Service.Metrics" = {
      display_name = "Oliver metrics connector workload"
      description  = "Submit governed operational and realized-value observations."
      member_types = ["Application"]
    }
  }

  user_role_values = toset([
    "Oliver.Admin.Read",
    "Oliver.Assessment.Test",
    "Oliver.Lifecycle.Approve",
    "Oliver.Scout.Review",
    "Oliver.Platform.Admin",
  ])

  admin_group_assignments = {
    for assignment in flatten([
      for role, group_ids in var.admin_role_group_object_ids : [
        for group_id in group_ids : {
          key      = "${role}:${group_id}"
          role     = role
          group_id = group_id
        }
      ]
    ]) : assignment.key => assignment
    if contains(local.user_role_values, assignment.role)
  }
}

resource "random_uuid" "oliver_api_identifier" {}
resource "random_uuid" "oliver_user_scope" {}

resource "random_uuid" "oliver_app_roles" {
  for_each = local.oliver_app_roles
}

resource "azuread_application" "oliver_api" {
  display_name     = "Oliver API (${var.environment})"
  description      = "Protected Oliver lifecycle API and workload boundary."
  identifier_uris  = ["api://${random_uuid.oliver_api_identifier.result}"]
  owners           = [data.azurerm_client_config.current.object_id]
  sign_in_audience = "AzureADMyOrg"

  api {
    requested_access_token_version = 2

    oauth2_permission_scope {
      admin_consent_description  = "Allow the Oliver admin dashboard to access Oliver on behalf of the signed-in user."
      admin_consent_display_name = "Access Oliver"
      enabled                    = true
      id                         = random_uuid.oliver_user_scope.result
      type                       = "User"
      user_consent_description   = "Allow this dashboard to access Oliver on your behalf."
      user_consent_display_name  = "Access Oliver"
      value                      = "access_as_user"
    }
  }

  dynamic "app_role" {
    for_each = local.oliver_app_roles

    content {
      allowed_member_types = app_role.value.member_types
      description          = app_role.value.description
      display_name         = app_role.value.display_name
      enabled              = true
      id                   = random_uuid.oliver_app_roles[app_role.key].result
      value                = app_role.key
    }
  }
}

resource "azuread_service_principal" "oliver_api" {
  client_id                    = azuread_application.oliver_api.client_id
  app_role_assignment_required = true
  owners                       = [data.azurerm_client_config.current.object_id]
}

resource "azuread_application" "admin_dashboard" {
  display_name     = "Oliver Admin Dashboard (${var.environment})"
  description      = "Browser SPA for authorized Oliver administrators and reviewers."
  owners           = [data.azurerm_client_config.current.object_id]
  sign_in_audience = "AzureADMyOrg"

  single_page_application {
    redirect_uris = setunion(toset([local.admin_frontend_origin]), var.admin_additional_redirect_uris)
  }

  required_resource_access {
    resource_app_id = azuread_application.oliver_api.client_id

    resource_access {
      id   = random_uuid.oliver_user_scope.result
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "admin_dashboard" {
  client_id = azuread_application.admin_dashboard.client_id
  owners    = [data.azurerm_client_config.current.object_id]
}

resource "azuread_app_role_assignment" "admin_groups" {
  for_each = local.admin_group_assignments

  app_role_id         = azuread_application.oliver_api.app_role_ids[each.value.role]
  principal_object_id = each.value.group_id
  resource_object_id  = azuread_service_principal.oliver_api.object_id
}

resource "azuread_app_role_assignment" "email_workflow" {
  app_role_id         = azuread_application.oliver_api.app_role_ids["Oliver.Service.Email"]
  principal_object_id = azurerm_user_assigned_identity.email_workflow.principal_id
  resource_object_id  = azuread_service_principal.oliver_api.object_id
}
